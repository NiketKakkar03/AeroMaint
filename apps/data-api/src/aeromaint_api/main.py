from typing import Literal

from fastapi import FastAPI
from pydantic import BaseModel

from aeromaint_api.api.v1 import router as v1_router
from aeromaint_api.config import get_settings


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    service: str = "data-api"
    environment: str


def create_app() -> FastAPI:
    settings = get_settings()
    application = FastAPI(
        title="AeroMaint Data API",
        version="0.1.0",
        description="Versioned platform API for multimodal capture sessions.",
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
