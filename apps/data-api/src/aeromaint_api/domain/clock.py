from collections.abc import Sequence
from dataclasses import dataclass

from aeromaint_api.domain.manifest import ClockDefinition, StreamGap


@dataclass(frozen=True)
class IndexedFrame:
    frame_number: int
    presentation_ns: int
    keyframe: bool


def map_to_session_time(source_ns: int, clock: ClockDefinition) -> int:
    return (
        clock.session_epoch_ns
        + ((source_ns - clock.source_epoch_ns) * clock.rate_numerator) // clock.rate_denominator
    )


def _inside_gap(time_ns: int, gaps: Sequence[StreamGap]) -> bool:
    return any(gap.start_ns <= time_ns < gap.end_ns for gap in gaps)


def frame_at_or_before(
    frames: Sequence[IndexedFrame], requested_ns: int, gaps: Sequence[StreamGap] = ()
) -> IndexedFrame | None:
    if _inside_gap(requested_ns, gaps):
        return None
    match = None
    for frame in frames:
        if frame.presentation_ns > requested_ns:
            break
        match = frame
    return match


def nearest_frame(
    frames: Sequence[IndexedFrame], requested_ns: int, gaps: Sequence[StreamGap] = ()
) -> IndexedFrame | None:
    if _inside_gap(requested_ns, gaps):
        return None
    return min(
        frames,
        key=lambda frame: (abs(frame.presentation_ns - requested_ns), frame.presentation_ns),
        default=None,
    )
