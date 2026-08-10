from typing import Any

from fastapi.testclient import TestClient

from aeromaint_api.domain.fixtures import FIXTURE_MANIFEST, FIXTURE_SESSION_ID
from aeromaint_api.main import app
from aeromaint_api.services.playback import InMemorySessionRepository, SessionRecord

client = TestClient(app)
base = FIXTURE_MANIFEST.start_ns


def test_session_and_stream_cursor_pagination() -> None:
    first = client.get("/v1/sessions", params={"limit": 1})
    assert first.status_code == 200
    assert first.json()["items"][0]["id"] == FIXTURE_SESSION_ID
    assert first.json()["next_cursor"] is None

    streams = client.get(f"/v1/sessions/{FIXTURE_SESSION_ID}/streams", params={"limit": 1}).json()
    assert [item["id"] for item in streams["items"]] == ["camera-left"]
    second = client.get(
        f"/v1/sessions/{FIXTURE_SESSION_ID}/streams",
        params={"limit": 1, "cursor": streams["next_cursor"]},
    )
    assert [item["id"] for item in second.json()["items"]] == ["imu-main"]


def test_invalid_cursor_is_a_typed_problem() -> None:
    response = client.get("/v1/sessions", params={"cursor": "not-a-cursor"})
    assert_problem(response, 400, "INVALID_CURSOR")


def test_manifest_has_immutable_etag_and_supports_conditional_get() -> None:
    response = client.get(f"/v1/sessions/{FIXTURE_SESSION_ID}/manifest")
    assert response.status_code == 200
    assert response.headers["cache-control"].endswith("immutable")
    assert response.headers["etag"].startswith('"')

    cached = client.get(
        f"/v1/sessions/{FIXTURE_SESSION_ID}/manifest",
        headers={"If-None-Match": response.headers["etag"]},
    )
    assert cached.status_code == 304
    assert cached.content == b""


def test_sample_range_is_start_inclusive_end_exclusive_and_can_be_empty() -> None:
    response = client.get(
        f"/v1/sessions/{FIXTURE_SESSION_ID}/streams/imu-main/samples",
        params={"start_ns": base, "end_ns": base + 5_000_000},
    )
    assert [item["timestamp_ns"] for item in response.json()["items"]] == [str(base)]
    assert response.json()["range"]["end_exclusive"] is True

    empty = client.get(
        f"/v1/sessions/{FIXTURE_SESSION_ID}/streams/imu-main/samples",
        params={"start_ns": base + 1, "end_ns": base + 2},
    )
    assert empty.status_code == 200
    assert empty.json()["items"] == []


def test_unsatisfiable_range_reports_available_bounds() -> None:
    response = client.get(
        f"/v1/sessions/{FIXTURE_SESSION_ID}/streams/imu-main/samples",
        params={"start_ns": base - 1, "end_ns": base + 1},
        headers={"X-Request-ID": "request-test", "X-Trace-ID": "trace-test"},
    )
    assert_problem(response, 416, "RANGE_NOT_SATISFIABLE")
    assert response.json()["request_id"] == "request-test"
    assert response.json()["trace_id"] == "trace-test"
    assert response.headers["x-request-id"] == "request-test"


def test_frame_at_defaults_to_at_or_before_and_nearest_is_explicit() -> None:
    default = client.get(
        f"/v1/sessions/{FIXTURE_SESSION_ID}/streams/camera-left/frame-at",
        params={"time_ns": base + 76_000_000},
    )
    assert default.json()["frame_number"] == 1
    assert default.json()["selection_mode"] == "at_or_before"

    nearest = client.get(
        f"/v1/sessions/{FIXTURE_SESSION_ID}/streams/camera-left/frame-at",
        params={"time_ns": base + 76_000_000, "mode": "nearest"},
    )
    assert nearest.json()["frame_number"] == 2


def test_frame_in_gap_is_typed_and_playback_index_is_paginated() -> None:
    gap = client.get(
        f"/v1/sessions/{FIXTURE_SESSION_ID}/streams/camera-left/frame-at",
        params={"time_ns": base + 100_000_000},
    )
    assert_problem(gap, 422, "FRAME_NOT_DECODABLE")

    index = client.get(
        f"/v1/sessions/{FIXTURE_SESSION_ID}/streams/camera-left/playback",
        params={"start_ns": base, "end_ns": base + 100_000_000, "limit": 1},
    ).json()
    assert [item["frame_number"] for item in index["items"]] == [0]
    assert index["next_cursor"] is not None


def test_gap_listing_and_stream_errors() -> None:
    gaps = client.get(f"/v1/sessions/{FIXTURE_SESSION_ID}/gaps")
    assert gaps.json()["items"][0]["stream_id"] == "camera-left"
    missing = client.get(f"/v1/sessions/{FIXTURE_SESSION_ID}/gaps?stream_id=missing")
    assert_problem(missing, 404, "STREAM_NOT_FOUND")


def test_repository_protocol_can_be_replaced_without_changing_api_models() -> None:
    replacement = InMemorySessionRepository()
    assert isinstance(replacement.sessions()[0], SessionRecord)


def test_openapi_contains_issue_8_surface() -> None:
    paths: dict[str, Any] = client.get("/openapi.json").json()["paths"]
    expected = {
        "/v1/sessions",
        "/v1/sessions/{session_id}",
        "/v1/sessions/{session_id}/manifest",
        "/v1/sessions/{session_id}/streams",
        "/v1/sessions/{session_id}/streams/{stream_id}/samples",
        "/v1/sessions/{session_id}/streams/{stream_id}/frame-at",
        "/v1/sessions/{session_id}/streams/{stream_id}/playback",
        "/v1/sessions/{session_id}/gaps",
    }
    assert expected <= paths.keys()


def assert_problem(response: Any, status: int, code: str) -> None:
    assert response.status_code == status
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["code"] == code
    assert response.json()["request_id"]
    assert response.json()["trace_id"]
