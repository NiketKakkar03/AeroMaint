from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI
from pydantic import BaseModel

from aeromaint_api.api.v1 import router as v1_router
from aeromaint_api.config import get_settings
from aeromaint_api.db import Database, MigrationRunner
from aeromaint_api.repositories import PostgresImportRepository


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    service: str = "data-api"
    environment: str


def create_app() -> FastAPI:
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

    @application.get("/health/live", response_model=HealthResponse, tags=["health"])
    async def live() -> HealthResponse:
        return HealthResponse(environment=settings.env)

    @application.get("/health/ready", response_model=HealthResponse, tags=["health"])
    async def ready() -> HealthResponse:
        return HealthResponse(environment=settings.env)

    application.include_router(v1_router)

    return application


app = create_app()
