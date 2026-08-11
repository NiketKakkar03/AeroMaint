from fastapi.testclient import TestClient

from aeromaint_api.main import app
from aeromaint_api.security.auth import create_development_token

AUTH = {"Authorization": f"Bearer {create_development_token(['viewer'])}"}


def test_deterministic_versioned_inference_and_abstentions() -> None:
    request = {
        "engine_id": "ENG-1",
        "session_id": "S-1",
        "observations": [
            {
                "timestamp_ns": str(index),
                "cycle": index,
                "features": {"vibration": 1.0 if index < 4 else 100.0},
            }
            for index in range(1, 5)
        ],
    }
    client = TestClient(app, headers=AUTH)
    headers = {"Idempotency-Key": "health-inference-eng-1"}
    first = client.post("/v1/health/inference", headers=headers, json=request)
    second = client.post("/v1/health/inference", headers=headers, json=request)
    assert first.status_code == 200
    assert first.json() == second.json()
    assert [point["status"] for point in first.json()["points"]] == [
        "insufficient_history",
        "insufficient_history",
        "ok",
        "ood",
    ]
    assert set(first.json()["versions"]) == {"model", "features", "data", "code"}


def test_fleet_ranking_and_engine_detail_expose_units_and_uncertainty() -> None:
    client = TestClient(app, headers=AUTH)
    fleet = client.get("/v1/health/fleet").json()
    assert fleet["ranking"] == "lowest_rul_first"
    assert all(
        item["rul_unit"] == "cycles" and len(item["interval"]) == 2 for item in fleet["items"]
    )
    detail = client.get("/v1/health/engines/ENG-101").json()
    assert detail["track"]["schema_version"] == "1.0.0"
