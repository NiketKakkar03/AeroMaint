import asyncio
import time
from collections import defaultdict, deque
from typing import Protocol

from aeromaint_api.security.errors import SecurityError


class RateLimiter(Protocol):
    async def check(self, subject: str) -> None: ...


class InMemoryRateLimiter:
    def __init__(self, limit: int, window_seconds: int) -> None:
        self._limit = limit
        self._window = window_seconds
        self._requests: dict[str, deque[float]] = defaultdict(deque)
        self._lock = asyncio.Lock()

    async def check(self, subject: str) -> None:
        now = time.monotonic()
        async with self._lock:
            requests = self._requests[subject]
            while requests and requests[0] <= now - self._window:
                requests.popleft()
            if len(requests) >= self._limit:
                raise SecurityError(
                    429,
                    "rate_limit_exceeded",
                    "Rate limit exceeded",
                    "Too many requests. Try again later.",
                    {"Retry-After": str(self._window)},
                )
            requests.append(now)
