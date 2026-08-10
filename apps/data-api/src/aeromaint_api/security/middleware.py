from collections.abc import Awaitable, Callable
from typing import cast
from uuid import uuid4

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response as StarletteResponse
from starlette.responses import StreamingResponse
from starlette.types import ASGIApp

from aeromaint_api.security.auth import Authenticator
from aeromaint_api.security.errors import SecurityError
from aeromaint_api.security.idempotency import CachedResponse, IdempotencyStore, request_fingerprint
from aeromaint_api.security.problems import problem_response
from aeromaint_api.security.rate_limit import RateLimiter

UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request.state.request_id = request.headers.get("X-Request-ID") or str(uuid4())
        response = await call_next(request)
        if "Cache-Control" not in response.headers:
            response.headers["Cache-Control"] = "no-store"
        response.headers.update(
            {
                "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
                "Referrer-Policy": "no-referrer",
                "X-Content-Type-Options": "nosniff",
                "X-Frame-Options": "DENY",
                "X-Request-ID": request.state.request_id,
            }
        )
        return response


class IdempotencyMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp, store: IdempotencyStore) -> None:
        super().__init__(app)
        self._store = store

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        if request.method not in UNSAFE_METHODS:
            return await call_next(request)
        try:
            return await self._dispatch_mutation(request, call_next)
        except SecurityError as exc:
            return problem_response(
                request, exc.status, exc.code, exc.title, exc.detail, exc.headers
            )

    async def _dispatch_mutation(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        authenticator: Authenticator = request.app.state.authenticator
        principal = authenticator.authenticate(request.headers.get("Authorization"))
        limiter: RateLimiter = request.app.state.rate_limiter
        await limiter.check(principal.subject)
        request.state.principal = principal
        key = request.headers.get("Idempotency-Key")
        if key is None:
            raise SecurityError(
                400,
                "idempotency_key_required",
                "Idempotency key required",
                "Mutating requests require an Idempotency-Key header.",
            )
        has_invalid_character = any(
            ord(character) < 33 or ord(character) > 126 for character in key
        )
        if not 1 <= len(key) <= 128 or has_invalid_character:
            raise SecurityError(
                400,
                "invalid_idempotency_key",
                "Invalid idempotency key",
                "Idempotency-Key must contain 1 to 128 visible ASCII characters.",
            )
        body = await request.body()
        fingerprint = request_fingerprint(
            request.method, request.url.path, request.url.query.encode(), body
        )
        scope = principal.subject

        async def perform() -> CachedResponse:
            response = await call_next(request)
            streamed_response = cast(StreamingResponse, response)
            chunks = [chunk async for chunk in streamed_response.body_iterator]
            response_body = b"".join(
                chunk.encode() if isinstance(chunk, str) else bytes(chunk) for chunk in chunks
            )
            return CachedResponse(
                fingerprint,
                response.status_code,
                tuple(response.headers.items()),
                response_body,
            )

        cached, replayed = await self._store.execute(scope, key, fingerprint, perform)
        headers = dict(cached.headers)
        headers["Idempotency-Replayed"] = "true" if replayed else "false"
        return StarletteResponse(
            cached.body,
            status_code=cached.status_code,
            headers=headers,
            media_type=None,
        )
