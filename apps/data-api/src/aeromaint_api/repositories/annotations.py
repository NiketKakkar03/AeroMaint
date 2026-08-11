import asyncio
from collections import defaultdict
from copy import deepcopy
from datetime import UTC, datetime
from uuid import UUID

from aeromaint_api.repositories.models import Annotation, AuditEvent


class InMemoryAnnotationRepository:
    """Atomic reference repository used by local API and focused tests."""

    def __init__(self) -> None:
        self._items: dict[UUID, Annotation] = {}
        self._events: dict[UUID, list[AuditEvent]] = defaultdict(list)
        self._lock = asyncio.Lock()
        self._event_id = 0

    async def create(self, annotation: Annotation) -> Annotation:
        async with self._lock:
            if annotation.id in self._items:
                raise ValueError("annotation already exists")
            self._items[annotation.id] = deepcopy(annotation)
            self._append(annotation, "created")
            return deepcopy(annotation)

    async def get(self, annotation_id: UUID) -> Annotation | None:
        item = self._items.get(annotation_id)
        return None if item is None else deepcopy(item)

    async def update(self, annotation: Annotation, expected_version: int) -> Annotation | None:
        async with self._lock:
            current = self._items.get(annotation.id)
            if current is None or current.version != expected_version:
                return None
            self._items[annotation.id] = deepcopy(annotation)
            self._append(
                annotation, "reviewed" if annotation.status != current.status else "updated"
            )
            return deepcopy(annotation)

    async def list_for_session(self, session_id: str) -> list[Annotation]:
        return [
            deepcopy(item)
            for item in sorted(
                self._items.values(), key=lambda value: (value.start_ns, str(value.id))
            )
            if item.session_id == session_id
        ]

    async def history(self, annotation_id: UUID) -> list[AuditEvent]:
        return deepcopy(self._events.get(annotation_id, []))

    def _append(self, annotation: Annotation, action: str) -> None:
        self._event_id += 1
        self._events[annotation.id].append(
            AuditEvent(
                id=self._event_id,
                occurred_at=datetime.now(UTC),
                actor=annotation.actor,
                action=f"annotation.{action}",
                entity_type="annotation",
                entity_id=str(annotation.id),
                payload={
                    "version": annotation.version,
                    "status": annotation.status,
                    "snapshot": annotation.model_dump(mode="json"),
                },
            )
        )
