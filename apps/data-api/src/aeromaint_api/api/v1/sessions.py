import hashlib
from typing import Annotated, Any, Literal, cast

from fastapi import APIRouter, Header, Query, Request, Response

from aeromaint_api.domain.manifest import CaptureSessionManifest, CaptureStream
from aeromaint_api.errors import ApiProblem
from aeromaint_api.services.playback import (
    SessionRecord,
    SessionRepository,
    frame_dict,
    page,
    select_frame,
    stream_for,
)

router = APIRouter(prefix="/sessions", tags=["sessions"])

Limit = Annotated[int, Query(ge=1, le=100)]
Timestamp = Annotated[int, Query(ge=-(2**63), le=2**63 - 1)]


def repository(request: Request) -> SessionRepository:
    return cast(SessionRepository, request.app.state.session_repository)


def session_or_404(request: Request, session_id: str) -> SessionRecord:
    record = repository(request).session(session_id)
    if record is None:
        raise ApiProblem(
            404, "SESSION_NOT_FOUND", "Session not found", f"Session '{session_id}' does not exist."
        )
    return record


def stream_or_404(
    request: Request, session_id: str, stream_id: str
) -> tuple[SessionRecord, CaptureStream]:
    record = session_or_404(request, session_id)
    stream = stream_for(record, stream_id)
    if stream is None:
        raise ApiProblem(
            404,
            "STREAM_NOT_FOUND",
            "Stream not found",
            f"Stream '{stream_id}' does not exist in session '{session_id}'.",
        )
    return record, stream


def checked_window(start_ns: int, end_ns: int, lower: int, upper: int) -> None:
    if start_ns >= end_ns or start_ns < lower or end_ns > upper:
        raise ApiProblem(
            416,
            "RANGE_NOT_SATISFIABLE",
            "Range not satisfiable",
            "Ranges are start-inclusive and end-exclusive and must lie within the stream bounds.",
            {"available_range": {"start_ns": str(lower), "end_ns": str(upper)}},
        )


def invalid_cursor() -> ApiProblem:
    return ApiProblem(400, "INVALID_CURSOR", "Invalid cursor", "The pagination cursor is invalid.")


@router.get("")
async def list_sessions(
    request: Request, limit: Limit = 50, cursor: str | None = None
) -> dict[str, Any]:
    try:
        records, next_cursor = page(repository(request).sessions(), cursor, limit)
    except ValueError as error:
        raise invalid_cursor() from error
    return {
        "items": [session_summary(item) for item in records],
        "next_cursor": next_cursor,
    }


def session_summary(record: SessionRecord) -> dict[str, Any]:
    manifest = record.manifest
    return {
        "id": manifest.session_id,
        "display_name": manifest.display_name,
        "start_ns": str(manifest.start_ns),
        "end_ns": str(manifest.end_ns),
        "stream_count": len(manifest.streams),
        "created_at": record.created_at,
    }


@router.get("/{session_id}")
async def get_session(request: Request, session_id: str) -> dict[str, Any]:
    return session_summary(session_or_404(request, session_id))


@router.get("/{session_id}/manifest", response_model=CaptureSessionManifest)
async def get_session_manifest(
    request: Request,
    session_id: str,
    if_none_match: Annotated[str | None, Header()] = None,
) -> Response:
    manifest = session_or_404(request, session_id).manifest
    content = manifest.model_dump_json(by_alias=True)
    etag = f'"{hashlib.sha256(content.encode()).hexdigest()}"'
    headers = {"ETag": etag, "Cache-Control": "public, max-age=31536000, immutable"}
    if if_none_match == etag:
        return Response(status_code=304, headers=headers)
    return Response(content, media_type="application/json", headers=headers)


@router.get("/{session_id}/streams")
async def list_streams(
    request: Request,
    session_id: str,
    limit: Limit = 50,
    cursor: str | None = None,
) -> dict[str, Any]:
    streams = session_or_404(request, session_id).manifest.streams
    try:
        items, next_cursor = page(streams, cursor, limit)
    except ValueError as error:
        raise invalid_cursor() from error
    return {
        "items": [item.model_dump(mode="json") for item in items],
        "next_cursor": next_cursor,
    }


@router.get("/{session_id}/streams/{stream_id}/samples")
async def get_samples(
    request: Request,
    session_id: str,
    stream_id: str,
    start_ns: Timestamp,
    end_ns: Timestamp,
    limit: Limit = 100,
    cursor: str | None = None,
) -> dict[str, Any]:
    _, stream = stream_or_404(request, session_id, stream_id)
    checked_window(start_ns, end_ns, stream.start_ns, stream.end_ns)
    values = [
        sample
        for sample in repository(request).samples(session_id, stream_id)
        if start_ns <= sample.timestamp_ns < end_ns
    ]
    try:
        items, next_cursor = page(values, cursor, limit)
    except ValueError as error:
        raise invalid_cursor() from error
    return {
        "items": [
            {"timestamp_ns": str(item.timestamp_ns), "values": item.values} for item in items
        ],
        "next_cursor": next_cursor,
        "range": {"start_ns": str(start_ns), "end_ns": str(end_ns), "end_exclusive": True},
        "schema_ref": stream.schema_ref,
        "downsampling": {"applied": False},
    }


@router.get("/{session_id}/streams/{stream_id}/frame-at")
async def get_frame_at(
    request: Request,
    session_id: str,
    stream_id: str,
    time_ns: Timestamp,
    mode: Literal["at_or_before", "nearest"] = "at_or_before",
) -> dict[str, Any]:
    _, stream = stream_or_404(request, session_id, stream_id)
    if time_ns < stream.start_ns or time_ns > stream.end_ns:
        raise ApiProblem(
            416,
            "RANGE_NOT_SATISFIABLE",
            "Time not satisfiable",
            "The requested time lies outside the stream bounds.",
            {"available_range": {"start_ns": str(stream.start_ns), "end_ns": str(stream.end_ns)}},
        )
    frame = select_frame(
        repository(request).frames(session_id, stream_id), time_ns, stream.gaps, mode
    )
    if frame is None:
        raise ApiProblem(
            422,
            "FRAME_NOT_DECODABLE",
            "Frame not decodable",
            "No valid frame satisfies the requested time and selection mode.",
        )
    return {**frame_dict(frame), "selection_mode": mode, "requested_ns": str(time_ns)}


@router.get("/{session_id}/streams/{stream_id}/playback")
async def get_playback_index(
    request: Request,
    session_id: str,
    stream_id: str,
    start_ns: Timestamp,
    end_ns: Timestamp,
    limit: Limit = 100,
    cursor: str | None = None,
) -> dict[str, Any]:
    _, stream = stream_or_404(request, session_id, stream_id)
    checked_window(start_ns, end_ns, stream.start_ns, stream.end_ns)
    frames = [
        frame
        for frame in repository(request).frames(session_id, stream_id)
        if start_ns <= frame.presentation_ns < end_ns
    ]
    try:
        items, next_cursor = page(frames, cursor, limit)
    except ValueError as error:
        raise invalid_cursor() from error
    return {
        "items": [frame_dict(item) for item in items],
        "next_cursor": next_cursor,
        "range": {"start_ns": str(start_ns), "end_ns": str(end_ns), "end_exclusive": True},
    }


@router.get("/{session_id}/gaps")
async def get_gaps(
    request: Request,
    session_id: str,
    stream_id: str | None = None,
) -> dict[str, Any]:
    record = session_or_404(request, session_id)
    streams = record.manifest.streams
    if stream_id is not None:
        _, selected = stream_or_404(request, session_id, stream_id)
        streams = [selected]
    return {
        "items": [
            {"stream_id": stream.id, **gap.model_dump(mode="json")}
            for stream in streams
            for gap in stream.gaps
        ]
    }
