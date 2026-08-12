import time
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Literal
from uuid import uuid4

import structlog
from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

from aeromaint_api.api.v1 import router as v1_router
from aeromaint_api.api.v1.copilot import create_workflow
from aeromaint_api.config import get_settings
from aeromaint_api.db import Database, MigrationRunner
from aeromaint_api.errors import ApiProblem
from aeromaint_api.errors import problem_response as api_problem_response
from aeromaint_api.repositories import PostgresImportRepository
from aeromaint_api.repositories.annotations import InMemoryAnnotationRepository
from aeromaint_api.repositories.exports import InMemoryExportRepository
from aeromaint_api.repositories.postgres import (
    PostgresAnnotationRepository,
    PostgresExportRepository,
)
from aeromaint_api.security.audit import AuditSink, InMemoryAppendOnlyAuditSink
from aeromaint_api.security.auth import Authenticator, DevelopmentJwtAuthenticator
from aeromaint_api.security.errors import SecurityError
from aeromaint_api.security.idempotency import IdempotencyStore, InMemoryIdempotencyStore
from aeromaint_api.security.middleware import IdempotencyMiddleware, SecurityHeadersMiddleware
from aeromaint_api.security.problems import problem_response as security_problem_response
from aeromaint_api.security.rate_limit import InMemoryRateLimiter, RateLimiter
from aeromaint_api.services.playback import (
    EmptySessionRepository,
    InMemorySessionRepository,
    SessionRepository,
)

logger = structlog.get_logger("aeromaint_api")
structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.JSONRenderer(),
    ]
)


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    service: str = "data-api"
    environment: str


def create_app(
    repository: SessionRepository | None = None,
    *,
    authenticator: Authenticator | None = None,
    audit_sink: AuditSink | None = None,
    rate_limiter: RateLimiter | None = None,
    idempotency_store: IdempotencyStore | None = None,
) -> FastAPI:
    settings = get_settings()
    if authenticator is None:
        if settings.env == "production":
            raise RuntimeError("A production Authenticator implementation must be supplied")
        authenticator = DevelopmentJwtAuthenticator(
            settings.jwt_secret, settings.jwt_issuer, settings.jwt_audience
        )

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        if settings.database_url is not None:
            database = Database(settings.database_url)
            if settings.migrate_on_startup:
                await MigrationRunner(database).upgrade()
            application.state.database = database
            application.state.import_repository = PostgresImportRepository(database)
            application.state.annotation_repository = PostgresAnnotationRepository(database)
            application.state.export_repository = PostgresExportRepository(database)
        yield

    application = FastAPI(
        title="AeroMaint Data API",
        version="0.1.0",
        description="Versioned platform API for multimodal capture sessions.",
        lifespan=lifespan,
    )
    application.state.session_repository = repository or (
        EmptySessionRepository() if settings.empty_state else InMemorySessionRepository()
    )
    application.state.annotation_repository = InMemoryAnnotationRepository()
    application.state.export_repository = InMemoryExportRepository()
    application.state.copilot_workflow = create_workflow()
    application.state.authenticator = authenticator
    application.state.audit_sink = audit_sink or InMemoryAppendOnlyAuditSink()
    application.state.rate_limiter = rate_limiter or InMemoryRateLimiter(
        settings.rate_limit_requests, settings.rate_limit_window_seconds
    )
    application.add_middleware(
        IdempotencyMiddleware, store=idempotency_store or InMemoryIdempotencyStore()
    )
    application.add_middleware(SecurityHeadersMiddleware)

    @application.middleware("http")
    async def request_context(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request.state.request_id = request.headers.get("x-request-id") or str(uuid4())
        request.state.trace_id = request.headers.get("x-trace-id") or request.state.request_id
        started = time.perf_counter()
        response = await call_next(request)
        duration = time.perf_counter() - started
        response.headers["X-Request-ID"] = request.state.request_id
        response.headers["X-Trace-ID"] = request.state.trace_id
        logger.info(
            "http_request",
            service="data-api",
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            duration_ms=round(duration * 1000, 3),
            request_id=request.state.request_id,
            trace_id=request.state.trace_id,
        )
        application.state.request_count = getattr(application.state, "request_count", 0) + 1
        application.state.request_duration = (
            getattr(application.state, "request_duration", 0.0) + duration
        )
        return response

    @application.exception_handler(ApiProblem)
    async def handle_problem(request: Request, problem: ApiProblem) -> JSONResponse:
        return api_problem_response(request, problem)

    @application.exception_handler(SecurityError)
    async def security_error(request: Request, exc: SecurityError) -> JSONResponse:
        return security_problem_response(
            request, exc.status, exc.code, exc.title, exc.detail, exc.headers
        )

    @application.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        return api_problem_response(
            request,
            ApiProblem(422, "INVALID_REQUEST", "Invalid request", str(exc)),
        )

    @application.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        return api_problem_response(
            request,
            ApiProblem(
                exc.status_code,
                "HTTP_ERROR",
                "HTTP error",
                str(exc.detail),
                headers=exc.headers,
            ),
        )

    @application.get("/health/live", response_model=HealthResponse, tags=["health"])
    async def live() -> HealthResponse:
        return HealthResponse(environment=settings.env)

    @application.get("/health/ready", response_model=HealthResponse, tags=["health"])
    async def ready() -> HealthResponse:
        database = getattr(application.state, "database", None)
        if database is not None:
            await database.check()
        return HealthResponse(environment=settings.env)

    @application.get("/metrics", include_in_schema=False)
    async def metrics() -> Response:
        count = getattr(application.state, "request_count", 0)
        duration = getattr(application.state, "request_duration", 0.0)
        body = (
            "# HELP aeromaint_http_requests_total HTTP requests handled.\n"
            "# TYPE aeromaint_http_requests_total counter\n"
            f'aeromaint_http_requests_total{{service="data-api"}} {count}\n'
            "# HELP aeromaint_http_request_duration_seconds_sum Request latency sum.\n"
            "# TYPE aeromaint_http_request_duration_seconds_sum counter\n"
            f'aeromaint_http_request_duration_seconds_sum{{service="data-api"}} {duration:.6f}\n'
            'aeromaint_build_info{service="data-api",version="0.1.0"} 1\n'
        )
        return Response(body, media_type="text/plain; version=0.0.4")

    application.include_router(v1_router)
    return application


app = create_app()
