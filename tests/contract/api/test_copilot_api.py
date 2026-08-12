from fastapi.testclient import TestClient

from aeromaint_api.main import create_app
from aeromaint_api.security.auth import create_development_token


def headers(role: str, key: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {create_development_token([role])}",
        "Idempotency-Key": key,
    }


def test_copilot_draft_persists_and_engineer_approves() -> None:
    client = TestClient(create_app())
    created = client.post(
        "/v1/copilot/runs",
        headers=headers("analyst", "create-run"),
        json={"session_id": "demo", "question": "What engine RUL and inspection guidance applies?"},
    )
    assert created.status_code == 201
    run = created.json()
    assert run["status"] == "draft"
    assert run["recommendation"]["claims"][0]["citations"]
    assert (
        client.post(
            f"/v1/copilot/runs/{run['id']}/review",
        headers=headers("analyst", "analyst-review"),
            json={"action": "approved", "expected_version": 1},
        ).status_code
        == 403
    )
    approved = client.post(
        f"/v1/copilot/runs/{run['id']}/review",
        headers=headers("engineer", "engineer-review"),
        json={"action": "approved", "expected_version": 1},
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"
    listed = client.get(
        "/v1/copilot/runs?session_id=demo", headers=headers("viewer", "list-runs")
    )
    assert listed.json()["items"][0]["status"] == "approved"
