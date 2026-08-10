from collections.abc import Callable
from typing import Annotated
from uuid import uuid4

from fastapi import Depends, Request

from aeromaint_api.security.audit import AuditSink, audit_event
from aeromaint_api.security.auth import Authenticator
from aeromaint_api.security.errors import SecurityError
from aeromaint_api.security.models import Permission, Principal
from aeromaint_api.security.rate_limit import RateLimiter


async def authenticated_principal(request: Request) -> Principal:
    existing = getattr(request.state, "principal", None)
    if isinstance(existing, Principal):
        return existing
    authenticator: Authenticator = request.app.state.authenticator
    principal = authenticator.authenticate(request.headers.get("Authorization"))
    limiter: RateLimiter = request.app.state.rate_limiter
    await limiter.check(principal.subject)
    request.state.principal = principal
    return principal


PrincipalDependency = Annotated[Principal, Depends(authenticated_principal)]


def require(permission: Permission) -> Callable[..., object]:
    async def authorized(request: Request, principal: PrincipalDependency) -> Principal:
        request_id = getattr(request.state, "request_id", str(uuid4()))
        sink: AuditSink = request.app.state.audit_sink
        allowed = permission in principal.permissions
        await sink.append(
            audit_event(
                principal.subject,
                permission.value,
                request.url.path,
                "allowed" if allowed else "denied",
                request_id,
            )
        )
        if not allowed:
            raise SecurityError(
                403,
                "permission_denied",
                "Permission denied",
                f"Permission '{permission.value}' is required.",
            )
        return principal

    return authorized
