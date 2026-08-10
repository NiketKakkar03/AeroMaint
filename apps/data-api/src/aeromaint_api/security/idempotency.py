import asyncio
import hashlib
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Protocol

from aeromaint_api.security.errors import SecurityError


@dataclass(frozen=True, slots=True)
class CachedResponse:
    fingerprint: str
    status_code: int
    headers: tuple[tuple[str, str], ...]
    body: bytes


class IdempotencyStore(Protocol):
    async def execute(
        self,
        scope: str,
        key: str,
        fingerprint: str,
        operation: Callable[[], Awaitable[CachedResponse]],
    ) -> tuple[CachedResponse, bool]: ...


class InMemoryIdempotencyStore:
    """Serializes a key's first operation and returns its immutable response thereafter."""

    def __init__(self) -> None:
        self._records: dict[tuple[str, str], CachedResponse] = {}
        self._locks: dict[tuple[str, str], asyncio.Lock] = {}
        self._guard = asyncio.Lock()

    async def execute(
        self,
        scope: str,
        key: str,
        fingerprint: str,
        operation: Callable[[], Awaitable[CachedResponse]],
    ) -> tuple[CachedResponse, bool]:
        record_key = (scope, key)
        async with self._guard:
            lock = self._locks.setdefault(record_key, asyncio.Lock())
        async with lock:
            existing = self._records.get(record_key)
            if existing is not None:
                if existing.fingerprint != fingerprint:
                    raise SecurityError(
                        409,
                        "idempotency_key_reused",
                        "Idempotency key conflict",
                        "This idempotency key was already used for a different request.",
                    )
                return existing, True
            response = await operation()
            if response.status_code < 500:
                self._records[record_key] = response
            return response, False


def request_fingerprint(method: str, path: str, query: bytes, body: bytes) -> str:
    digest = hashlib.sha256()
    for part in (method.encode(), path.encode(), query, body):
        digest.update(len(part).to_bytes(8, "big"))
        digest.update(part)
    return digest.hexdigest()
