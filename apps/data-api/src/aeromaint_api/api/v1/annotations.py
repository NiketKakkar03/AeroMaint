from datetime import UTC, datetime
from typing import Annotated, Any, Literal, cast
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, Request
from pydantic import BaseModel, Field, model_validator

from aeromaint_api.api.v1.sessions import session_or_404
from aeromaint_api.errors import ApiProblem
from aeromaint_api.repositories.interfaces import AnnotationRepository
from aeromaint_api.repositories.models import Annotation
from aeromaint_api.security.dependencies import require
from aeromaint_api.security.models import Permission, Principal

router = APIRouter(prefix="/sessions/{session_id}/annotations", tags=["annotations"])


class AnnotationBody(BaseModel):
    start_ns: int
    end_ns: int | None = None
    kind: str = Field(min_length=1, max_length=100)
    stream_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    provenance: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def interval(self) -> "AnnotationBody":
        end = self.start_ns if self.end_ns is None else self.end_ns
        if end < self.start_ns:
            raise ValueError("end_ns must be greater than or equal to start_ns")
        self.end_ns = end
        return self


class AnnotationPatch(AnnotationBody):
    expected_version: int = Field(ge=1)


class ReviewBody(BaseModel):
    expected_version: int = Field(ge=1)
    decision: Literal["approved", "rejected"]
    comment: str | None = Field(default=None, max_length=2000)


def repository(request: Request) -> AnnotationRepository:
    return cast(AnnotationRepository, request.app.state.annotation_repository)


def validate_bounds(request: Request, session_id: str, body: AnnotationBody) -> None:
    manifest = session_or_404(request, session_id).manifest
    if body.start_ns < manifest.start_ns or cast(int, body.end_ns) > manifest.end_ns:
        raise ApiProblem(
            416,
            "ANNOTATION_OUT_OF_RANGE",
            "Annotation out of range",
            "Annotation times must reference the canonical session timeline.",
            {
                "available_range": {
                    "start_ns": str(manifest.start_ns),
                    "end_ns": str(manifest.end_ns),
                }
            },
        )
    if body.stream_id is not None and all(
        stream.id != body.stream_id for stream in manifest.streams
    ):
        raise ApiProblem(
            422,
            "STREAM_NOT_FOUND",
            "Stream not found",
            f"Stream '{body.stream_id}' does not exist in this session.",
        )


def response(item: Annotation) -> dict[str, Any]:
    value = item.model_dump(mode="json")
    value["start_ns"] = str(item.start_ns)
    value["end_ns"] = str(item.end_ns)
    value["shape"] = "point" if item.start_ns == item.end_ns else "interval"
    return value


@router.get("", dependencies=[Depends(require(Permission.ANNOTATION_READ))])
async def list_annotations(request: Request, session_id: str) -> dict[str, Any]:
    session_or_404(request, session_id)
    return {
        "items": [response(item) for item in await repository(request).list_for_session(session_id)]
    }


@router.post("", status_code=201)
async def create_annotation(
    request: Request,
    session_id: str,
    body: AnnotationBody,
    principal: Annotated[Principal, Depends(require(Permission.ANNOTATION_DRAFT))],
) -> dict[str, Any]:
    validate_bounds(request, session_id, body)
    now = datetime.now(UTC)
    item = Annotation(
        id=uuid4(),
        session_id=session_id,
        stream_id=body.stream_id,
        start_ns=body.start_ns,
        end_ns=cast(int, body.end_ns),
        kind=body.kind,
        payload=body.payload,
        actor=principal.subject,
        provenance=body.provenance,
        created_at=now,
        updated_at=now,
    )
    return response(await repository(request).create(item))


async def current_or_404(request: Request, session_id: str, annotation_id: UUID) -> Annotation:
    item = await repository(request).get(annotation_id)
    if item is None or item.session_id != session_id:
        raise ApiProblem(
            404, "ANNOTATION_NOT_FOUND", "Annotation not found", "Annotation does not exist."
        )
    return item


def expected_version(body_version: int, if_match: str | None) -> int:
    if if_match is None:
        return body_version
    try:
        header_version = int(if_match.strip('"W/'))
    except ValueError as error:
        raise ApiProblem(
            400, "INVALID_VERSION", "Invalid version", "If-Match must contain an integer version."
        ) from error
    if header_version != body_version:
        raise ApiProblem(
            400, "VERSION_MISMATCH", "Version mismatch", "If-Match and expected_version disagree."
        )
    return header_version


@router.put("/{annotation_id}")
async def update_annotation(
    request: Request,
    session_id: str,
    annotation_id: UUID,
    body: AnnotationPatch,
    principal: Annotated[Principal, Depends(require(Permission.ANNOTATION_DRAFT))],
    if_match: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    validate_bounds(request, session_id, body)
    current = await current_or_404(request, session_id, annotation_id)
    version = expected_version(body.expected_version, if_match)
    updated = current.model_copy(
        update={
            "stream_id": body.stream_id,
            "start_ns": body.start_ns,
            "end_ns": cast(int, body.end_ns),
            "kind": body.kind,
            "payload": body.payload,
            "provenance": body.provenance,
            "actor": principal.subject,
            "version": version + 1,
            "updated_at": datetime.now(UTC),
        }
    )
    saved = await repository(request).update(updated, version)
    if saved is None:
        latest = await current_or_404(request, session_id, annotation_id)
        raise ApiProblem(
            409,
            "ANNOTATION_VERSION_CONFLICT",
            "Annotation changed",
            "A newer annotation version exists; reload before editing.",
            {"current_version": latest.version},
        )
    return response(saved)


@router.post("/{annotation_id}/review")
async def review_annotation(
    request: Request,
    session_id: str,
    annotation_id: UUID,
    body: ReviewBody,
    principal: Annotated[Principal, Depends(require(Permission.ANNOTATION_REVIEW))],
    if_match: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    current = await current_or_404(request, session_id, annotation_id)
    version = expected_version(body.expected_version, if_match)
    payload = {**current.payload, "review": {"comment": body.comment}}
    updated = current.model_copy(
        update={
            "status": body.decision,
            "payload": payload,
            "actor": principal.subject,
            "version": version + 1,
            "updated_at": datetime.now(UTC),
        }
    )
    saved = await repository(request).update(updated, version)
    if saved is None:
        latest = await current_or_404(request, session_id, annotation_id)
        raise ApiProblem(
            409,
            "ANNOTATION_VERSION_CONFLICT",
            "Annotation changed",
            "A newer annotation version exists; reload before reviewing.",
            {"current_version": latest.version},
        )
    return response(saved)


@router.get("/{annotation_id}/history", dependencies=[Depends(require(Permission.ANNOTATION_READ))])
async def annotation_history(
    request: Request, session_id: str, annotation_id: UUID
) -> dict[str, Any]:
    await current_or_404(request, session_id, annotation_id)
    return {
        "items": [
            event.model_dump(mode="json")
            for event in await repository(request).history(annotation_id)
        ]
    }
