from fastapi.testclient import TestClient

from aeromaint_api.domain.fixtures import FIXTURE_SESSION_ID
from aeromaint_api.main import app


def test_fixture_manifest_uses_decimal_string_timestamps() -> None:
    response = TestClient(app).get(f"/v1/sessions/{FIXTURE_SESSION_ID}/manifest")

    assert response.status_code == 200
    payload = response.json()
    assert payload["schema_version"] == "1.0.0"
    assert payload["session_id"] == FIXTURE_SESSION_ID
    assert payload["start_ns"] == "9007199254740993"


def test_unknown_session_has_stable_error_code() -> None:
    response = TestClient(app).get("/v1/sessions/missing/manifest")

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "session_not_found"


def test_openapi_exposes_versioned_manifest_endpoint() -> None:
    schema = TestClient(app).get("/openapi.json").json()

    assert "/v1/sessions/{session_id}/manifest" in schema["paths"]
