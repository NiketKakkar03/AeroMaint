import time
from pathlib import Path

import pyarrow.ipc as ipc
from fastapi.testclient import TestClient

from aeromaint_api.config import get_settings
from aeromaint_api.domain.fixtures import FIXTURE_MANIFEST, FIXTURE_SESSION_ID
from aeromaint_api.main import create_app
from aeromaint_api.security.auth import create_development_token


def headers(
    subject: str = "exporter", role: str = "analyst", key: str = "export-1"
) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {create_development_token([role], subject=subject)}",
        "Idempotency-Key": key,
    }


def wait(client: TestClient, export_id: str, auth: dict[str, str]) -> dict[str, object]:
    for _ in range(100):
        response = client.get(f"/v1/exports/{export_id}", headers=auth)
        assert response.status_code == 200
        job = response.json()
        if job["status"] not in {"pending", "running"}:
            return job
        time.sleep(0.01)
    raise AssertionError("export did not finish")


def test_arrow_export_is_half_open_idempotent_authorized_and_round_trips(tmp_path: Path) -> None:
    get_settings.cache_clear()
    settings = get_settings()
    object.__setattr__(settings, "export_root", str(tmp_path))
    start = FIXTURE_MANIFEST.start_ns
    body = {
        "session_id": FIXTURE_SESSION_ID,
        "start_ns": str(start),
        "end_ns": str(start + 10_000_000),
        "stream_ids": ["imu-main"],
        "sensor_format": "arrow",
    }
    with TestClient(create_app()) as client:
        created = client.post("/v1/exports", headers=headers(), json=body)
        duplicate = client.post("/v1/exports", headers=headers(), json=body)
        assert created.status_code == 202
        # The global idempotency middleware replays the original accepted response.
        assert duplicate.status_code == 202
        assert duplicate.json()["id"] == created.json()["id"]
        job = wait(client, created.json()["id"], headers())
        assert job["status"] == "succeeded"
        assert job["window_semantics"] == "[start_ns,end_ns)"
        assert (
            client.get(f"/v1/exports/{job['id']}", headers=headers("other", key="x")).status_code
            == 404
        )
        manifest = job["manifest"]
        assert manifest["window"]["semantics"] == "[start_ns,end_ns)"
        arrow = tmp_path / str(job["id"]) / "imu-main.arrow"
        table = ipc.open_stream(arrow).read_all()
        timestamps = table.column("timestamp_ns").to_pylist()
        assert timestamps == [start, start + 5_000_000]
        assert all(start <= value < start + 10_000_000 for value in timestamps)


def test_cancel_is_idempotent_and_permission_checked() -> None:
    with TestClient(create_app()) as client:
        repository = client.app.state.export_repository
        # A pending request can race to completion; cancellation remains safe
        # in either terminal state.
        start = FIXTURE_MANIFEST.start_ns
        response = client.post(
            "/v1/exports",
            headers=headers(key="cancel"),
            json={
                "session_id": FIXTURE_SESSION_ID,
                "start_ns": str(start),
                "end_ns": str(start + 10_000_000),
                "stream_ids": ["imu-main"],
            },
        )
        export_id = response.json()["id"]
        denied = client.delete(
            f"/v1/exports/{export_id}", headers=headers("viewer", "viewer", "denied")
        )
        assert denied.status_code == 403
        first = client.delete(f"/v1/exports/{export_id}", headers=headers(key="cancel-1"))
        second = client.delete(f"/v1/exports/{export_id}", headers=headers(key="cancel-2"))
        assert first.status_code == second.status_code == 200
        assert first.json()["status"] in {"cancelled", "succeeded"}
        assert repository is not None


def test_rejects_empty_or_out_of_range_windows() -> None:
    with TestClient(create_app()) as client:
        base = {"session_id": FIXTURE_SESSION_ID, "stream_ids": ["imu-main"]}
        empty = client.post(
            "/v1/exports",
            headers=headers(key="empty"),
            json={**base, "start_ns": "1", "end_ns": "1"},
        )
        outside = client.post(
            "/v1/exports",
            headers=headers(key="outside"),
            json={
                **base,
                "start_ns": str(FIXTURE_MANIFEST.start_ns - 1),
                "end_ns": str(FIXTURE_MANIFEST.start_ns + 1),
            },
        )
        assert empty.status_code == 422
        assert outside.status_code == 416
