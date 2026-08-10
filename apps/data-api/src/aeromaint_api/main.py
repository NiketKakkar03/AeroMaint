from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Literal
from uuid import uuid4

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

from aeromaint_api.api.v1 import router as v1_router
from aeromaint_api.config import get_settings
from aeromaint_api.db import Database, MigrationRunner
from aeromaint_api.repositories import PostgresImportRepository
from aeromaint_api.errors import ApiProblem, problem_response
from aeromaint_api.services.playback import InMemorySessionRepository, SessionRepository


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    service: str = "data-api"
    environment: str


def create_app(repository: SessionRepository | None = None) -> FastAPI:
    settings = get_settings()

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        if settings.database_url is not None:
            database = Database(settings.database_url)
            if settings.migrate_on_startup:
                await MigrationRunner(database).upgrade()
            application.state.database = database
            application.state.import_repository = PostgresImportRepository(database)
        yield

    application = FastAPI(
        title="AeroMaint Data API",
        version="0.1.0",
        description="Versioned platform API for multimodal capture sessions.",
        lifespan=lifespan,
    )
    application.state.session_repository = repository or InMemorySessionRepository()

    @application.middleware("http")
    async def request_context(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request.state.request_id = request.headers.get("x-request-id") or str(uuid4())
        request.state.trace_id = request.headers.get("x-trace-id") or request.state.request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        response.headers["X-Trace-ID"] = request.state.trace_id
        return response

    @application.exception_handler(ApiProblem)
    async def handle_problem(request: Request, problem: ApiProblem) -> JSONResponse:
        return problem_response(request, problem)

    @application.exception_handler(RequestValidationError)
    async def handle_validation(request: Request, error: RequestValidationError) -> JSONResponse:
        return problem_response(
            request,
            ApiProblem(422, "INVALID_REQUEST", "Invalid request", str(error)),
        )

    @application.exception_handler(StarletteHTTPException)
    async def handle_http_error(request: Request, error: StarletteHTTPException) -> JSONResponse:
        return problem_response(
            request,
            ApiProblem(error.status_code, "HTTP_ERROR", "HTTP error", str(error.detail)),
        )

    @application.get("/health/live", response_model=HealthResponse, tags=["health"])
    async def live() -> HealthResponse:
        return HealthResponse(environment=settings.env)

    @application.get("/health/ready", response_model=HealthResponse, tags=["health"])
    async def ready() -> HealthResponse:
        return HealthResponse(environment=settings.env)

    application.include_router(v1_router)

    return application


app = create_app()
