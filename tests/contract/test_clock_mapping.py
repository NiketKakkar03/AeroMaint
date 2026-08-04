import hashlib
import json
from pathlib import Path
from typing import Any

from scripts.generate_sync_fixture import build_fixture

from aeromaint_api.domain.clock import (
    IndexedFrame,
    frame_at_or_before,
    map_to_session_time,
    nearest_frame,
)
from aeromaint_api.domain.manifest import CaptureSessionManifest

FIXTURE = Path(__file__).parents[1] / "media-fixtures" / "synthetic-session"


def load_json(name: str) -> dict[str, Any]:
    return json.loads((FIXTURE / name).read_text())


def load_frames(name: str) -> list[IndexedFrame]:
    return [
        IndexedFrame(
            frame_number=frame["frame_number"],
            presentation_ns=int(frame["presentation_ns"]),
            keyframe=frame["keyframe"],
        )
        for frame in load_json(name)["frames"]
    ]


def test_shared_clock_mapping_expectations() -> None:
    manifest = CaptureSessionManifest.model_validate(load_json("manifest.json"))
    expectations = load_json("expectations.json")
    clocks = {clock.id: clock for clock in manifest.clocks}

    for expectation in expectations["clock_mappings"]:
        assert map_to_session_time(
            int(expectation["source_ns"]), clocks[expectation["clock_id"]]
        ) == int(expectation["expected_session_ns"])


def test_shared_frame_lookup_and_gap_expectations() -> None:
    manifest = CaptureSessionManifest.model_validate(load_json("manifest.json"))
    expectations = load_json("expectations.json")
    frames = load_frames("camera-left-index.json")
    stream = next(stream for stream in manifest.streams if stream.id == "camera-left")
    base_ns = int(expectations["base_ns"])

    for query in expectations["frame_queries"]:
        requested_ns = base_ns + int(query["offset_ns"])
        before = frame_at_or_before(frames, requested_ns, stream.gaps)
        nearest = nearest_frame(frames, requested_ns, stream.gaps)
        assert (before.frame_number if before else None) == query["at_or_before"]
        assert (nearest.frame_number if nearest else None) == query["nearest"]


def test_generator_output_and_checksums_are_reproducible() -> None:
    generated = build_fixture()
    for name, payload in generated.items():
        assert (FIXTURE / name).read_bytes() == payload

    expected_checksums = "".join(
        f"{hashlib.sha256(payload).hexdigest()}  {name}\n"
        for name, payload in sorted(generated.items())
    )
    assert (FIXTURE / "SHA256SUMS").read_text() == expected_checksums
