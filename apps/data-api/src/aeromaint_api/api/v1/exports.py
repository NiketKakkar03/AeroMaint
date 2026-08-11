import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated, Any, Literal, cast
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, Request, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, model_validator

from aeromaint_api.api.v1.sessions import session_or_404
from aeromaint_api.config import get_settings
from aeromaint_api.errors import ApiProblem
from aeromaint_api.repositories.exports import InMemoryExportRepository
from aeromaint_api.repositories.models import ExportJob, ExportStatus
from aeromaint_api.security.dependencies import require
from aeromaint_api.security.models import Permission, Principal, Role
from aeromaint_worker.exports import ExportCancelled, ExportProcessor

router = APIRouter(prefix="/exports", tags=["exports"])


class ExportBody(BaseModel):
    session_id: str = Field(min_length=1)
    start_ns: int
    end_ns: int
    stream_ids: list[str] = Field(default_factory=list)
    sensor_format: Literal["arrow", "json"] = "arrow"
    include_annotations: bool = True

    @model_validator(mode="after")
    def window(self) -> "ExportBody":
        if self.end_ns <= self.start_ns:
            raise ValueError("end_ns must be greater than start_ns; exports use [start_ns,end_ns)")
        return self


def repo(request: Request) -> InMemoryExportRepository:
    return cast(InMemoryExportRepository, request.app.state.export_repository)


def ensure_owner(job: ExportJob, principal: Principal) -> None:
    if job.actor != principal.subject and Role.ADMIN not in principal.roles:
        raise ApiProblem(404, "EXPORT_NOT_FOUND", "Export not found", "Export does not exist.")


def payload(job: ExportJob) -> dict[str, Any]:
    result = job.model_dump(mode="json")
    result["start_ns"] = str(job.start_ns)
    result["end_ns"] = str(job.end_ns)
    result["window_semantics"] = "[start_ns,end_ns)"
    result["status_url"] = f"/v1/exports/{job.id}"
    if job.status == ExportStatus.SUCCEEDED:
        result["manifest_url"] = f"/v1/exports/{job.id}/files/manifest.json"
    return result


async def process(app: Any, job: ExportJob) -> None:
    repository: InMemoryExportRepository = app.state.export_repository
    await repository.update(job.id, status=ExportStatus.RUNNING, progress=0.05)
    processor = ExportProcessor(app.state.session_repository, Path(get_settings().export_root))

    async def cancelled() -> bool:
        current = await repository.get(job.id)
        return current is None or current.cancel_requested

    try:
        annotations = [
            item.model_dump(mode="json")
            for item in await app.state.annotation_repository.list_for_session(job.session_id)
        ]
        manifest = await processor.run(job, cancelled, annotations)
        if await cancelled():
            raise ExportCancelled
        await repository.update(
            job.id, status=ExportStatus.SUCCEEDED, progress=1, manifest=manifest
        )
    except ExportCancelled:
        processor.remove_partial(processor.root, str(job.id))
        await repository.update(job.id, status=ExportStatus.CANCELLED, progress=0)
    except Exception as error:
        await repository.update(job.id, status=ExportStatus.FAILED, error={"message": str(error)})


@router.post("", status_code=202)
async def create_export(
    body: ExportBody,
    request: Request,
    response: Response,
    principal: Annotated[Principal, Depends(require(Permission.EXPORT_CREATE))],
    idempotency_key: Annotated[str, Header(min_length=1)],
) -> dict[str, Any]:
    session = session_or_404(request, body.session_id).manifest
    if body.start_ns < session.start_ns or body.end_ns > session.end_ns:
        raise ApiProblem(
            416,
            "EXPORT_OUT_OF_RANGE",
            "Export out of range",
            "Export window must be inside the canonical session range.",
            {
                "available_range": {
                    "start_ns": str(session.start_ns),
                    "end_ns": str(session.end_ns),
                },
                "window_semantics": "[start_ns,end_ns)",
            },
        )
    ids = body.stream_ids or [stream.id for stream in session.streams]
    unknown = sorted(set(ids) - {stream.id for stream in session.streams})
    if unknown:
        raise ApiProblem(
            422, "STREAM_NOT_FOUND", "Stream not found", f"Unknown streams: {', '.join(unknown)}"
        )
    now = datetime.now(UTC)
    job = ExportJob(
        id=uuid4(),
        idempotency_key=idempotency_key,
        session_id=body.session_id,
        actor=principal.subject,
        start_ns=body.start_ns,
        end_ns=body.end_ns,
        stream_ids=ids,
        sensor_format=body.sensor_format,
        include_annotations=body.include_annotations,
        created_at=now,
        updated_at=now,
        expires_at=now + timedelta(seconds=get_settings().export_ttl_seconds),
    )
    saved, created = await repo(request).create(job)
    if created:
        task = asyncio.create_task(process(request.app, saved))
        request.app.state.export_tasks = getattr(request.app.state, "export_tasks", set())
        request.app.state.export_tasks.add(task)
        task.add_done_callback(request.app.state.export_tasks.discard)
    else:
        response.status_code = 200
    return payload(saved)


@router.get("/{export_id}")
async def get_export(
    export_id: UUID,
    request: Request,
    principal: Annotated[Principal, Depends(require(Permission.EXPORT_READ))],
) -> dict[str, Any]:
    job = await repo(request).get(export_id)
    if job is None:
        raise ApiProblem(404, "EXPORT_NOT_FOUND", "Export not found", "Export does not exist.")
    ensure_owner(job, principal)
    return payload(job)


@router.delete("/{export_id}")
async def cancel_export(
    export_id: UUID,
    request: Request,
    principal: Annotated[Principal, Depends(require(Permission.EXPORT_CANCEL))],
) -> dict[str, Any]:
    job = await repo(request).get(export_id)
    if job is None:
        raise ApiProblem(404, "EXPORT_NOT_FOUND", "Export not found", "Export does not exist.")
    ensure_owner(job, principal)
    return payload(cast(ExportJob, await repo(request).cancel(export_id)))


@router.get("/{export_id}/files/{filename}")
async def export_file(
    export_id: UUID,
    filename: str,
    request: Request,
    principal: Annotated[Principal, Depends(require(Permission.EXPORT_READ))],
) -> FileResponse:
    job = await repo(request).get(export_id)
    if job is None:
        raise ApiProblem(404, "EXPORT_NOT_FOUND", "Export not found", "Export does not exist.")
    ensure_owner(job, principal)
    if job.status != ExportStatus.SUCCEEDED:
        raise ApiProblem(
            409, "EXPORT_NOT_READY", "Export not ready", "Export output is not available."
        )
    safe = Path(filename).name
    path = Path(get_settings().export_root) / str(export_id) / safe
    if not path.is_file():
        raise ApiProblem(
            404, "EXPORT_FILE_NOT_FOUND", "Export file not found", "Export artifact does not exist."
        )
    return FileResponse(path)
