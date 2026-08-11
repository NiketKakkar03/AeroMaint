from typing import Any
from uuid import UUID, uuid4

from psycopg.types.json import Jsonb

from aeromaint_api.db import Database
from aeromaint_api.domain.manifest import CaptureSessionManifest
from aeromaint_api.repositories.models import (
    Annotation,
    AuditEvent,
    ExportJob,
    ImportJob,
    ImportStatus,
)


class PostgresSessionRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    async def put(self, manifest: CaptureSessionManifest) -> None:
        async with self.database.connection() as connection, connection.transaction():
            await connection.execute(
                """INSERT INTO sessions(id, display_name, start_ns, end_ns, manifest)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET display_name=EXCLUDED.display_name,
                start_ns=EXCLUDED.start_ns, end_ns=EXCLUDED.end_ns, manifest=EXCLUDED.manifest""",
                (
                    manifest.session_id,
                    manifest.display_name,
                    manifest.start_ns,
                    manifest.end_ns,
                    Jsonb(manifest.model_dump(mode="json")),
                ),
            )
            await connection.execute(
                "DELETE FROM streams WHERE session_id = %s", (manifest.session_id,)
            )
            await connection.execute(
                "DELETE FROM artifacts WHERE session_id = %s", (manifest.session_id,)
            )
            for artifact in manifest.artifacts:
                await connection.execute(
                    """INSERT INTO artifacts
                    (id, session_id, media_type, logical_key, size_bytes, sha256)
                    VALUES (%s, %s, %s, %s, %s, %s)""",
                    (
                        artifact.id,
                        manifest.session_id,
                        artifact.media_type,
                        artifact.logical_key,
                        artifact.size_bytes,
                        artifact.sha256,
                    ),
                )
            for stream in manifest.streams:
                await connection.execute(
                    """INSERT INTO streams
                    (id, session_id, kind, clock_id, start_ns, end_ns, sample_count, schema_ref)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                    (
                        stream.id,
                        manifest.session_id,
                        stream.kind,
                        stream.clock_id,
                        stream.start_ns,
                        stream.end_ns,
                        stream.sample_count,
                        stream.schema_ref,
                    ),
                )
                for artifact_id in stream.artifact_ids:
                    await connection.execute(
                        """INSERT INTO stream_artifacts(session_id, stream_id, artifact_id)
                        VALUES (%s,%s,%s)""",
                        (manifest.session_id, stream.id, artifact_id),
                    )
                for gap in stream.gaps:
                    await connection.execute(
                        """INSERT INTO gaps(session_id, stream_id, start_ns, end_ns, reason)
                        VALUES (%s, %s, %s, %s, %s)""",
                        (manifest.session_id, stream.id, gap.start_ns, gap.end_ns, gap.reason),
                    )

    async def get(self, session_id: str) -> CaptureSessionManifest | None:
        async with self.database.connection() as connection:
            cursor = await connection.execute(
                "SELECT manifest FROM sessions WHERE id = %s", (session_id,)
            )
            row = await cursor.fetchone()
        return None if row is None else CaptureSessionManifest.model_validate(row["manifest"])


class PostgresImportRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    async def create(self, idempotency_key: str, source_uri: str) -> tuple[ImportJob, bool]:
        import_id = uuid4()
        async with self.database.connection() as connection, connection.transaction():
            cursor = await connection.execute(
                """INSERT INTO imports(id, idempotency_key, source_uri) VALUES (%s, %s, %s)
                ON CONFLICT (idempotency_key) DO NOTHING RETURNING *""",
                (import_id, idempotency_key, source_uri),
            )
            row = await cursor.fetchone()
            created = row is not None
            if row is None:
                cursor = await connection.execute(
                    "SELECT * FROM imports WHERE idempotency_key = %s", (idempotency_key,)
                )
                row = await cursor.fetchone()
        if row is None:
            raise RuntimeError("idempotent import row disappeared")
        return ImportJob.model_validate(row), created

    async def get(self, import_id: UUID) -> ImportJob | None:
        async with self.database.connection() as connection:
            cursor = await connection.execute("SELECT * FROM imports WHERE id = %s", (import_id,))
            row = await cursor.fetchone()
        return None if row is None else ImportJob.model_validate(row)


class PostgresExportRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    async def create(self, job: ExportJob) -> tuple[ExportJob, bool]:
        async with self.database.connection() as connection, connection.transaction():
            cursor = await connection.execute(
                """INSERT INTO exports(id,idempotency_key,session_id,actor,start_ns,end_ns,
                stream_ids,sensor_format,include_annotations,expires_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (actor,idempotency_key) DO NOTHING RETURNING *""",
                (
                    job.id,
                    job.idempotency_key,
                    job.session_id,
                    job.actor,
                    job.start_ns,
                    job.end_ns,
                    Jsonb(job.stream_ids),
                    job.sensor_format,
                    job.include_annotations,
                    job.expires_at,
                ),
            )
            row = await cursor.fetchone()
            created = row is not None
            if row is None:
                cursor = await connection.execute(
                    "SELECT * FROM exports WHERE actor=%s AND idempotency_key=%s",
                    (job.actor, job.idempotency_key),
                )
                row = await cursor.fetchone()
        if row is None:
            raise RuntimeError("idempotent export row disappeared")
        return ExportJob.model_validate(row), created

    async def get(self, export_id: UUID) -> ExportJob | None:
        async with self.database.connection() as connection, connection.transaction():
            await connection.execute(
                """UPDATE exports SET status='expired',updated_at=now()
                WHERE id=%s AND expires_at<=now() AND status NOT IN ('cancelled','expired')""",
                (export_id,),
            )
            cursor = await connection.execute("SELECT * FROM exports WHERE id=%s", (export_id,))
            row = await cursor.fetchone()
        return None if row is None else ExportJob.model_validate(row)

    async def update(self, export_id: UUID, **values: object) -> ExportJob | None:
        allowed = {"status", "progress", "cancel_requested", "manifest", "error"}
        selected = {key: value for key, value in values.items() if key in allowed}
        if not selected:
            return await self.get(export_id)
        assignments = ",".join(f"{key}=%s" for key in selected)
        params = [
            Jsonb(value) if key in {"manifest", "error"} and value is not None else value
            for key, value in selected.items()
        ]
        async with self.database.connection() as connection, connection.transaction():
            cursor = await connection.execute(
                f"UPDATE exports SET {assignments},updated_at=now() WHERE id=%s RETURNING *",  # noqa: S608
                (*params, export_id),
            )
            row = await cursor.fetchone()
        return None if row is None else ExportJob.model_validate(row)

    async def cancel(self, export_id: UUID) -> ExportJob | None:
        async with self.database.connection() as connection, connection.transaction():
            cursor = await connection.execute(
                """UPDATE exports SET cancel_requested=true,status='cancelled',updated_at=now()
                WHERE id=%s AND status IN ('pending','running','cancelled') RETURNING *""",
                (export_id,),
            )
            row = await cursor.fetchone()
            if row is None:
                cursor = await connection.execute("SELECT * FROM exports WHERE id=%s", (export_id,))
                row = await cursor.fetchone()
        return None if row is None else ExportJob.model_validate(row)

    async def set_status(
        self,
        import_id: UUID,
        status: ImportStatus,
        *,
        session_id: str | None = None,
        error: dict[str, Any] | None = None,
    ) -> ImportJob | None:
        async with self.database.connection() as connection, connection.transaction():
            cursor = await connection.execute(
                """UPDATE imports SET status=%s, session_id=%s, error=%s, updated_at=now()
                WHERE id=%s RETURNING *""",
                (status, session_id, Jsonb(error) if error is not None else None, import_id),
            )
            row = await cursor.fetchone()
        return None if row is None else ImportJob.model_validate(row)


class PostgresAnnotationRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    async def create(self, annotation: Annotation) -> Annotation:
        async with self.database.connection() as connection, connection.transaction():
            cursor = await connection.execute(
                """INSERT INTO annotations
                (id,session_id,stream_id,start_ns,end_ns,kind,payload,version,status,actor,provenance)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *""",
                (
                    annotation.id,
                    annotation.session_id,
                    annotation.stream_id,
                    annotation.start_ns,
                    annotation.end_ns,
                    annotation.kind,
                    Jsonb(annotation.payload),
                    annotation.version,
                    annotation.status,
                    annotation.actor,
                    Jsonb(annotation.provenance),
                ),
            )
            row = await cursor.fetchone()
            await self._audit(connection, annotation, "annotation.created")
        return Annotation.model_validate(row)

    async def get(self, annotation_id: UUID) -> Annotation | None:
        async with self.database.connection() as connection:
            cursor = await connection.execute(
                "SELECT * FROM annotations WHERE id=%s", (annotation_id,)
            )
            row = await cursor.fetchone()
        return None if row is None else Annotation.model_validate(row)

    async def update(self, annotation: Annotation, expected_version: int) -> Annotation | None:
        async with self.database.connection() as connection, connection.transaction():
            cursor = await connection.execute(
                """UPDATE annotations SET stream_id=%s,start_ns=%s,end_ns=%s,kind=%s,payload=%s,
                version=%s,status=%s,actor=%s,provenance=%s,updated_at=%s
                WHERE id=%s AND version=%s RETURNING *""",
                (
                    annotation.stream_id,
                    annotation.start_ns,
                    annotation.end_ns,
                    annotation.kind,
                    Jsonb(annotation.payload),
                    annotation.version,
                    annotation.status,
                    annotation.actor,
                    Jsonb(annotation.provenance),
                    annotation.updated_at,
                    annotation.id,
                    expected_version,
                ),
            )
            row = await cursor.fetchone()
            if row is not None:
                action = (
                    "annotation.reviewed"
                    if annotation.status in {"approved", "rejected"}
                    else "annotation.updated"
                )
                await self._audit(connection, annotation, action)
        return None if row is None else Annotation.model_validate(row)

    async def list_for_session(self, session_id: str) -> list[Annotation]:
        async with self.database.connection() as connection:
            cursor = await connection.execute(
                "SELECT * FROM annotations WHERE session_id=%s ORDER BY created_at,id",
                (session_id,),
            )
            rows = await cursor.fetchall()
        return [Annotation.model_validate(row) for row in rows]

    async def history(self, annotation_id: UUID) -> list[AuditEvent]:
        async with self.database.connection() as connection:
            cursor = await connection.execute(
                """SELECT * FROM audit_events WHERE entity_type='annotation' AND entity_id=%s
                ORDER BY occurred_at,id""",
                (str(annotation_id),),
            )
            rows = await cursor.fetchall()
        return [AuditEvent.model_validate(row) for row in rows]

    @staticmethod
    async def _audit(connection: Any, annotation: Annotation, action: str) -> None:
        await connection.execute(
            """INSERT INTO audit_events(actor,action,entity_type,entity_id,payload)
            VALUES (%s,%s,'annotation',%s,%s)""",
            (
                annotation.actor,
                action,
                str(annotation.id),
                Jsonb(
                    {
                        "version": annotation.version,
                        "status": annotation.status,
                        "snapshot": annotation.model_dump(mode="json"),
                    }
                ),
            ),
        )


class PostgresAuditRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    async def append(
        self, actor: str, action: str, entity_type: str, entity_id: str, payload: dict[str, Any]
    ) -> AuditEvent:
        async with self.database.connection() as connection, connection.transaction():
            cursor = await connection.execute(
                """INSERT INTO audit_events(actor,action,entity_type,entity_id,payload)
                VALUES (%s,%s,%s,%s,%s) RETURNING *""",
                (actor, action, entity_type, entity_id, Jsonb(payload)),
            )
            row = await cursor.fetchone()
        return AuditEvent.model_validate(row)

    async def list_for_entity(self, entity_type: str, entity_id: str) -> list[AuditEvent]:
        async with self.database.connection() as connection:
            cursor = await connection.execute(
                """SELECT * FROM audit_events WHERE entity_type=%s AND entity_id=%s
                ORDER BY occurred_at,id""",
                (entity_type, entity_id),
            )
            rows = await cursor.fetchall()
        return [AuditEvent.model_validate(row) for row in rows]
