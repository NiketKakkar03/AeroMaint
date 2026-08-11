from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from aeromaint_api.services.health import demo_track, engine_summary, infer_track

router = APIRouter(prefix="/health", tags=["health-inference"])


class Observation(BaseModel):
    timestamp_ns: str = Field(pattern=r"^-?\d+$")
    cycle: int = Field(ge=0)
    features: dict[str, float]


class InferenceRequest(BaseModel):
    engine_id: str = Field(min_length=1)
    session_id: str = Field(min_length=1)
    observations: list[Observation]


@router.post("/inference")
async def inference(request: InferenceRequest) -> dict[str, Any]:
    return infer_track(
        request.engine_id, request.session_id, [item.model_dump() for item in request.observations]
    )


@router.get("/fleet")
async def fleet() -> dict[str, Any]:
    items = [
        engine_summary(demo_track(engine, f"session-{engine.lower()}"))
        for engine in ("ENG-101", "ENG-204", "ENG-309")
    ]
    items.sort(key=lambda item: (item["rul"] is None, item["rul"] or 0))
    return {"items": items, "ranking": "lowest_rul_first", "rul_unit": "cycles"}


@router.get("/engines/{engine_id}")
async def engine(engine_id: str) -> dict[str, Any]:
    track = demo_track(engine_id, f"session-{engine_id.lower()}")
    return {**engine_summary(track), "track": track}


@router.get("/sessions/{session_id}/model-track")
async def session_track(session_id: str, engine_id: str = "ENG-101") -> dict[str, Any]:
    return demo_track(engine_id, session_id)
