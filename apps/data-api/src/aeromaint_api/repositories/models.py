from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class ImportStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class ImportJob(BaseModel):
    id: UUID
    idempotency_key: str
    source_uri: str
    status: ImportStatus
    session_id: str | None = None
    error: dict[str, Any] | None = None
    created_at: datetime
    updated_at: datetime


class ExportStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class ExportJob(BaseModel):
    id: UUID
    idempotency_key: str
    session_id: str
    actor: str
    start_ns: int
    end_ns: int
    stream_ids: list[str]
    sensor_format: str = "arrow"
    include_annotations: bool = True
    status: ExportStatus = ExportStatus.PENDING
    progress: float = 0
    cancel_requested: bool = False
    manifest: dict[str, Any] | None = None
    error: dict[str, Any] | None = None
    created_at: datetime
    updated_at: datetime
    expires_at: datetime


class Annotation(BaseModel):
    id: UUID
    session_id: str
    stream_id: str | None = None
    start_ns: int
    end_ns: int
    kind: str
    payload: dict[str, Any] = Field(default_factory=dict)
    version: int = 1
    status: str = "draft"
    actor: str
    provenance: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class AuditEvent(BaseModel):
    id: int
    occurred_at: datetime
    actor: str
    action: str
    entity_type: str
    entity_id: str
    payload: dict[str, Any] = Field(default_factory=dict)
