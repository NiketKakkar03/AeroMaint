import asyncio
from datetime import UTC, datetime
from uuid import UUID

from aeromaint_api.repositories.models import ExportJob, ExportStatus


class InMemoryExportRepository:
    def __init__(self) -> None:
        self._jobs: dict[UUID, ExportJob] = {}
        self._keys: dict[tuple[str, str], UUID] = {}
        self._lock = asyncio.Lock()

    async def create(self, job: ExportJob) -> tuple[ExportJob, bool]:
        async with self._lock:
            existing = self._keys.get((job.actor, job.idempotency_key))
            if existing is not None:
                return self._jobs[existing], False
            self._jobs[job.id] = job
            self._keys[(job.actor, job.idempotency_key)] = job.id
            return job, True

    async def get(self, export_id: UUID) -> ExportJob | None:
        async with self._lock:
            job = self._jobs.get(export_id)
            if (
                job is not None
                and job.status not in {ExportStatus.CANCELLED, ExportStatus.EXPIRED}
                and job.expires_at <= datetime.now(UTC)
            ):
                job = job.model_copy(update={"status": ExportStatus.EXPIRED})
                self._jobs[export_id] = job
            return job

    async def update(self, export_id: UUID, **values: object) -> ExportJob | None:
        async with self._lock:
            current = self._jobs.get(export_id)
            if current is None:
                return None
            job = current.model_copy(update={**values, "updated_at": datetime.now(UTC)})
            self._jobs[export_id] = job
            return job

    async def cancel(self, export_id: UUID) -> ExportJob | None:
        async with self._lock:
            current = self._jobs.get(export_id)
            if current is None:
                return None
            if current.status in {
                ExportStatus.SUCCEEDED,
                ExportStatus.FAILED,
                ExportStatus.EXPIRED,
            }:
                return current
            job = current.model_copy(
                update={
                    "cancel_requested": True,
                    "status": ExportStatus.CANCELLED,
                    "updated_at": datetime.now(UTC),
                }
            )
            self._jobs[export_id] = job
            return job
