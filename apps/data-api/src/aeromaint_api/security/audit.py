import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol


@dataclass(frozen=True, slots=True)
class AuditEvent:
    occurred_at: datetime
    actor: str
    action: str
    resource: str
    outcome: str
    request_id: str


class AuditSink(Protocol):
    async def append(self, event: AuditEvent) -> None: ...


class InMemoryAppendOnlyAuditSink:
    def __init__(self) -> None:
        self._events: list[AuditEvent] = []
        self._lock = asyncio.Lock()

    async def append(self, event: AuditEvent) -> None:
        async with self._lock:
            self._events.append(event)

    async def snapshot(self) -> tuple[AuditEvent, ...]:
        async with self._lock:
            return tuple(self._events)


def audit_event(
    actor: str, action: str, resource: str, outcome: str, request_id: str
) -> AuditEvent:
    return AuditEvent(datetime.now(UTC), actor, action, resource, outcome, request_id)
