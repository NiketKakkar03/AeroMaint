from collections.abc import Iterable, Mapping
from typing import Any

from aeromaint_api.services.arrow import IMU_FIELDS, SensorSource, build_arrow_window


class CountingRepository:
    def __init__(self, session_rows: int) -> None:
        self.session_rows = session_rows
        self.visited = 0

    def describe(self, session_id: str, stream_id: str) -> SensorSource:
        return SensorSource(stream_id, "fixture://large", "f" * 64, IMU_FIELDS)

    def iter_window(
        self, session_id: str, stream_id: str, start_ns: int, end_ns: int
    ) -> Iterable[Mapping[str, Any]]:
        del session_id, stream_id
        for timestamp in range(self.session_rows):
            if timestamp < start_ns:
                continue
            if timestamp > end_ns:
                break
            self.visited += 1
            yield {"timestamp_ns": timestamp, "ax": 0.0, "ay": None, "az": 9.81}


def test_processing_is_bounded_by_requested_window_not_session_size() -> None:
    small_session = CountingRepository(10_000)
    large_session = CountingRepository(10_000_000)

    small = build_arrow_window(small_session, "s", "imu", 100, 199, max_points=None)
    large = build_arrow_window(large_session, "s", "imu", 100, 199, max_points=None)

    assert small is not None and large is not None
    assert small_session.visited == large_session.visited == 100
    assert len(small.body) == len(large.body)
