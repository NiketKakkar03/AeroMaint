from __future__ import annotations

import json
import time
from collections.abc import Callable, Iterator, Mapping
from threading import Event
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from .errors import CaptureError, CaptureHttpError, CaptureTransportError, Problem
from .models import ImuSample, ImuWindow, Page, SensorSample, SensorWindow, SessionSummary, StreamSummary

Open = Callable[..., Any]


class CaptureClient:
    """Synchronous client for the public v1 API. Nanoseconds are always Python ints."""

    def __init__(
        self,
        base_url: str,
        *,
        token: str | None = None,
        headers: Mapping[str, str] | None = None,
        timeout: float = 30.0,
        max_attempts: int = 3,
        backoff: float = 0.1,
        opener: Open = urlopen,
    ) -> None:
        if not base_url.startswith(("http://", "https://")):
            raise ValueError("base_url must be an HTTP(S) URL")
        if timeout <= 0 or max_attempts < 1 or backoff < 0:
            raise ValueError("timeout and max_attempts must be positive; backoff cannot be negative")
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_attempts = max_attempts
        self.backoff = backoff
        self.opener = opener
        self.headers = {"Accept": "application/json", **dict(headers or {})}
        if token is not None:
            self.headers["Authorization"] = f"Bearer {token}"

    def _get(self, path: str, cancel: Event | None) -> dict[str, Any]:
        if cancel is not None and cancel.is_set():
            raise CaptureError("Capture request was cancelled", code="cancelled")
        last: Exception | None = None
        for attempt in range(self.max_attempts):
            try:
                with self.opener(
                    Request(  # noqa: S310 - constructor validates HTTP(S) base_url
                        f"{self.base_url}{path}", headers=self.headers
                    ),
                    timeout=self.timeout,
                ) as response:
                    value = json.load(response)
                    if not isinstance(value, dict):
                        raise CaptureError("API response must be an object", code="INVALID_RESPONSE")
                    return value
            except HTTPError as error:
                problem = self._problem(error)
                retryable = error.code in {408, 429} or error.code >= 500
                last = CaptureHttpError(error.code, problem, retryable=retryable)
                if not retryable or attempt + 1 == self.max_attempts:
                    raise last from error
                retry_after = error.headers.get("Retry-After")
                delay = float(retry_after) if retry_after is not None else self._delay(attempt)
            except (TimeoutError, URLError, OSError) as error:
                last = CaptureTransportError(
                    f"Capture request failed: {error}", code="TRANSPORT_ERROR", retryable=True
                )
                if attempt + 1 == self.max_attempts:
                    raise last from error
                delay = self._delay(attempt)
            self._wait(delay, cancel)
        raise last or AssertionError("unreachable")

    def _delay(self, attempt: int) -> float:
        return self.backoff * (2**attempt)

    @staticmethod
    def _wait(delay: float, cancel: Event | None) -> None:
        if cancel is None:
            time.sleep(delay)
        elif cancel.wait(delay):
            raise CaptureError("Capture request was cancelled", code="cancelled")

    @staticmethod
    def _problem(error: HTTPError) -> Problem:
        try:
            raw = json.loads(error.read().decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            raw = {}
        return Problem(**{key: raw.get(key) for key in Problem.__dataclass_fields__})

    @staticmethod
    def _path(path: str, **query: object) -> str:
        values = {key: value for key, value in query.items() if value is not None}
        return f"{path}?{urlencode(values)}" if values else path

    def list_sessions(
        self, *, cursor: str | None = None, limit: int = 50, cancel: Event | None = None
    ) -> Page[SessionSummary]:
        self._validate_limit(limit)
        raw = self._get(self._path("/v1/sessions", cursor=cursor, limit=limit), cancel)
        return Page(
            tuple(
                SessionSummary(
                    id=str(item["id"]), start_ns=int(item["start_ns"]), end_ns=int(item["end_ns"]),
                    display_name=item.get("display_name"), stream_count=item.get("stream_count"),
                    created_at=item.get("created_at"),
                )
                for item in raw.get("items", [])
            ),
            raw.get("next_cursor"),
        )

    def iter_sessions(
        self, *, page_size: int = 50, max_items: int = 1000, cancel: Event | None = None
    ) -> Iterator[SessionSummary]:
        self._validate_limit(page_size)
        self._validate_limit(max_items)
        cursor = None
        emitted = 0
        while emitted < max_items:
            page = self.list_sessions(cursor=cursor, limit=min(page_size, max_items-emitted), cancel=cancel)
            for item in page.items:
                yield item
                emitted += 1
            if not page.items or not page.next_cursor or page.next_cursor == cursor:
                return
            cursor = page.next_cursor

    def list_streams(
        self, session_id: str, *, cursor: str | None = None, limit: int = 50,
        cancel: Event | None = None,
    ) -> Page[StreamSummary]:
        self._validate_limit(limit)
        raw = self._get(self._path(f"/v1/sessions/{quote(session_id, safe='')}/streams", cursor=cursor, limit=limit), cancel)
        return Page(tuple(StreamSummary(
            id=str(item["id"]), kind=str(item["kind"]), start_ns=int(item["start_ns"]),
            end_ns=int(item["end_ns"]), schema_ref=item.get("schema_ref")
        ) for item in raw.get("items", [])), raw.get("next_cursor"))

    def get_sensor_window(
        self, session_id: str, stream_id: str, *, start_ns: int, end_ns: int,
        cursor: str | None = None, limit: int = 100, cancel: Event | None = None,
    ) -> SensorWindow:
        if start_ns >= end_ns:
            raise ValueError("end_ns must be greater than start_ns; windows are [start_ns,end_ns)")
        self._validate_limit(limit)
        raw = self._get(self._path(
            f"/v1/sessions/{quote(session_id, safe='')}/streams/{quote(stream_id, safe='')}/samples",
            start_ns=start_ns, end_ns=end_ns, cursor=cursor, limit=limit,
        ), cancel)
        window = raw.get("range", {})
        return SensorWindow(
            session_id=session_id, stream_id=stream_id,
            start_ns=int(window.get("start_ns", start_ns)), end_ns=int(window.get("end_ns", end_ns)),
            samples=tuple(SensorSample(int(item["timestamp_ns"]), dict(item["values"])) for item in raw.get("items", [])),
            schema_ref=raw.get("schema_ref"), next_cursor=raw.get("next_cursor"),
            downsampled=bool(raw.get("downsampling", {}).get("applied", False)),
        )

    def get_imu_window(
        self, session_id: str, stream_id: str, *, start_ns: int, end_ns: int,
        cursor: str | None = None, limit: int = 100, cancel: Event | None = None,
    ) -> ImuWindow:
        """Return a typed IMU window while retaining any additive wire fields."""
        window = self.get_sensor_window(
            session_id, stream_id, start_ns=start_ns, end_ns=end_ns,
            cursor=cursor, limit=limit, cancel=cancel,
        )
        samples: list[ImuSample] = []
        for sample in window.samples:
            try:
                ax, ay, az = (float(sample.values[key]) for key in ("ax", "ay", "az"))
            except (KeyError, TypeError, ValueError) as error:
                raise CaptureError(
                    "IMU sample values must contain numeric ax, ay, and az",
                    code="INVALID_RESPONSE",
                ) from error
            samples.append(ImuSample(sample.timestamp_ns, ax, ay, az, sample.values))
        return ImuWindow(
            window.session_id, window.stream_id, window.start_ns, window.end_ns,
            tuple(samples), window.schema_ref, window.next_cursor, window.downsampled,
        )

    @staticmethod
    def _validate_limit(value: int) -> None:
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise ValueError("pagination limits must be positive integers")
