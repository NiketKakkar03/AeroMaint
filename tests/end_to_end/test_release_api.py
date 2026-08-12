import asyncio
import time
from collections.abc import Sequence

from fastapi.testclient import TestClient

from aeromaint_api.domain.clock import IndexedFrame
from aeromaint_api.main import create_app
from aeromaint_api.security.auth import create_development_token
from aeromaint_api.services.playback import Sample, SessionRecord


def bearer(role: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_development_token([role])}"}


class OutageRepository:
    def sessions(self) -> Sequence[SessionRecord]:
        raise ConnectionError("dependency unavailable")

    def session(self, session_id: str) -> SessionRecord | None:
        raise ConnectionError("dependency unavailable")

    def samples(self, session_id: str, stream_id: str) -> Sequence[Sample]:
        raise ConnectionError("dependency unavailable")

    def frames(self, session_id: str, stream_id: str) -> Sequence[IndexedFrame]:
        raise ConnectionError("dependency unavailable")


def test_core_api_playback_and_malformed_input_release_path() -> None:
    with TestClient(create_app()) as client:
        headers = bearer("viewer")
        sessions = client.get("/v1/sessions", headers=headers)
        assert sessions.status_code == 200
        session_id = sessions.json()["items"][0]["id"]
        manifest = client.get(f"/v1/sessions/{session_id}/manifest", headers=headers)
        assert manifest.status_code == 200
        stream = manifest.json()["streams"][0]
        malformed = client.get(
            f"/v1/sessions/{session_id}/streams/{stream['id']}/playback",
            params={"start_ns": "not-an-integer", "end_ns": stream["end_ns"]},
            headers=headers,
        )
        assert malformed.status_code == 422
        assert malformed.json()["code"] == "INVALID_REQUEST"


def test_dependency_outage_is_not_mistaken_for_empty_state() -> None:
    client = TestClient(create_app(repository=OutageRepository()), raise_server_exceptions=False)
    response = client.get("/v1/sessions", headers=bearer("viewer"))
    assert response.status_code == 500


def test_health_endpoint_stays_within_release_timeout_budget() -> None:
    async def probe() -> int:
        return await asyncio.wait_for(
            asyncio.to_thread(TestClient(create_app()).get, "/health/ready"), 1
        )

    started = time.monotonic()
    response = asyncio.run(probe())
    assert response.status_code == 200
    assert time.monotonic() - started < 1
