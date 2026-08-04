import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from aeromaint_api.domain.fixtures import FIXTURE_SESSION_ID
from aeromaint_api.domain.manifest import CaptureSessionManifest
from aeromaint_api.main import app

GOLDEN_FIXTURE = (
    Path(__file__).parents[3] / "tests" / "contract" / "fixtures" / "capture-manifest-v1.json"
)


def load_fixture() -> dict[str, Any]:
    return json.loads(GOLDEN_FIXTURE.read_text())


def test_fixture_manifest_matches_shared_golden_contract() -> None:
    response = TestClient(app).get(f"/v1/sessions/{FIXTURE_SESSION_ID}/manifest")

    assert response.status_code == 200
    assert response.json() == load_fixture()
    assert response.json()["start_ns"] == "9007199254740993"


def test_python_validator_consumes_shared_golden_fixture() -> None:
    manifest = CaptureSessionManifest.model_validate(load_fixture())

    assert manifest.start_ns == 9_007_199_254_740_993
    assert manifest.streams[0].gaps[0].reason == "missing"


@pytest.mark.parametrize(
    ("mutation", "expected"),
    [
        (lambda value: value["streams"][0].update(clock_id="unknown"), "unknown clock"),
        (lambda value: value.update(start_ns="9223372036854775808"), "less than or equal"),
        (
            lambda value: value["streams"][0]["gaps"].append(
                {
                    "start_ns": "9007199354740993",
                    "end_ns": "9007199394740993",
                    "reason": "corrupt",
                }
            ),
            "non-overlapping",
        ),
    ],
)
def test_python_validator_rejects_semantically_invalid_manifests(
    mutation: Any, expected: str
) -> None:
    candidate = load_fixture()
    mutation(candidate)

    with pytest.raises(ValidationError, match=expected):
        CaptureSessionManifest.model_validate(candidate)


def test_unknown_session_has_stable_error_code() -> None:
    response = TestClient(app).get("/v1/sessions/missing/manifest")

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "session_not_found"


def test_openapi_exposes_versioned_manifest_endpoint_and_string_timestamps() -> None:
    schema = TestClient(app).get("/openapi.json").json()

    assert "/v1/sessions/{session_id}/manifest" in schema["paths"]
    timestamp_schema = schema["components"]["schemas"]["CaptureSessionManifest"]["properties"][
        "start_ns"
    ]
    assert timestamp_schema["type"] == "string"
