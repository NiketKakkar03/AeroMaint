import hmac
from typing import Annotated, Any

from fastapi import APIRouter, Header, HTTPException, Query, Request, Response, status
from pydantic import BaseModel

from aeromaint_api.domain.fixtures import FIXTURE_SESSION_ID
from aeromaint_api.domain.transport import (
    FIXTURE_TOKEN,
    FRAME_INDEX,
    FixtureMediaRepository,
    FixtureSensorRepository,
)
from aeromaint_api.services.arrow import build_arrow_window
from aeromaint_api.services.ranges import InvalidRange, parse_byte_range, strong_etag

router = APIRouter(prefix="/sessions/{session_id}", tags=["transport"])
sensor_repository = FixtureSensorRepository()
media_repository = FixtureMediaRepository()


def _authorize(authorization: str | None) -> None:
    expected = f"Bearer {FIXTURE_TOKEN}"
    if authorization is None or not hmac.compare_digest(authorization, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "authentication_required"},
            headers={"WWW-Authenticate": "Bearer"},
        )


@router.get("/streams/{stream_id}/samples")
def get_sensor_window(
    session_id: str,
    stream_id: str,
    start_ns: Annotated[int, Query()],
    end_ns: Annotated[int, Query()],
    max_points: Annotated[int | None, Query(ge=1, le=100_000)] = None,
) -> Response:
    if end_ns < start_ns:
        raise HTTPException(422, detail={"code": "invalid_window"})
    result = build_arrow_window(
        sensor_repository,
        session_id,
        stream_id,
        start_ns,
        end_ns,
        max_points=max_points,
    )
    if result is None:
        raise HTTPException(404, detail={"code": "stream_not_found"})
    return Response(
        result.body,
        media_type="application/vnd.apache.arrow.stream",
        headers={
            "X-AeroMaint-Downsampling": result.mode,
            "X-AeroMaint-Input-Samples": str(result.input_sample_count),
            "X-AeroMaint-Output-Samples": str(result.output_sample_count),
            "Cache-Control": "private, no-cache",
        },
    )


class Frame(BaseModel):
    frame_number: int
    presentation_ns: str
    byte_offset: int
    byte_length: int
    keyframe: bool
    decodable_from_ns: str


class FrameIndex(BaseModel):
    schema_version: str = "1.0.0"
    stream_id: str
    frames: list[Frame]


@router.get("/streams/{stream_id}/frames", response_model=FrameIndex)
def get_frame_index(
    session_id: str,
    stream_id: str,
    start_ns: int | None = None,
    end_ns: int | None = None,
) -> FrameIndex:
    if session_id != FIXTURE_SESSION_ID or stream_id != "camera-left":
        raise HTTPException(404, detail={"code": "stream_not_found"})
    decodable_from = 0
    frames: list[Frame] = []
    for source in FRAME_INDEX:
        if source["keyframe"]:
            decodable_from = source["presentation_ns"]
        timestamp = source["presentation_ns"]
        if (start_ns is None or timestamp >= start_ns) and (end_ns is None or timestamp <= end_ns):
            values: dict[str, Any] = dict(source)
            values["presentation_ns"] = str(timestamp)
            values["decodable_from_ns"] = str(decodable_from)
            frames.append(Frame.model_validate(values))
    return FrameIndex(stream_id=stream_id, frames=frames)


@router.get("/media/{artifact_id}")
def get_media(
    session_id: str,
    artifact_id: str,
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> Response:
    _authorize(authorization)
    artifact = media_repository.get(session_id, artifact_id)
    if artifact is None:
        raise HTTPException(404, detail={"code": "artifact_not_found"})
    etag = strong_etag(artifact.data)
    common = {
        "Accept-Ranges": "bytes",
        "ETag": etag,
        "Cache-Control": "private, max-age=31536000, immutable",
    }
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers=common)
    range_header = request.headers.get("range")
    if range_header is None or request.headers.get("if-range", etag) != etag:
        return Response(artifact.data, media_type=artifact.media_type, headers=common)
    try:
        selected = parse_byte_range(range_header, len(artifact.data))
    except InvalidRange as error:
        raise HTTPException(
            416,
            detail={"code": "range_not_satisfiable"},
            headers={**common, "Content-Range": f"bytes */{len(artifact.data)}"},
        ) from error
    headers = {
        **common,
        "Content-Range": f"bytes {selected.start}-{selected.end}/{len(artifact.data)}",
    }
    return Response(
        artifact.data[selected.start : selected.end + 1],
        status_code=206,
        media_type=artifact.media_type,
        headers=headers,
    )
