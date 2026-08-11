import asyncio
from datetime import UTC, datetime
from uuid import uuid4

from fastapi.testclient import TestClient

from aeromaint_api.domain.fixtures import FIXTURE_MANIFEST, FIXTURE_SESSION_ID
from aeromaint_api.main import create_app
from aeromaint_api.repositories.models import Annotation
from aeromaint_api.security.auth import create_development_token


def headers(role: str, key: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {create_development_token([role], subject=f'{role}-user')}",
        "Idempotency-Key": key,
    }


def create(client: TestClient) -> dict[str, object]:
    response = client.post(
        f"/v1/sessions/{FIXTURE_SESSION_ID}/annotations",
        headers=headers("analyst", "create"),
        json={
            "start_ns": FIXTURE_MANIFEST.start_ns,
            "kind": "finding",
            "provenance": {"source": "test"},
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_point_interval_version_conflict_and_history() -> None:
    with TestClient(create_app()) as client:
        item = create(client)
        annotation_id = item["id"]
        update = {
            "start_ns": FIXTURE_MANIFEST.start_ns,
            "end_ns": FIXTURE_MANIFEST.start_ns + 1,
            "kind": "finding",
            "expected_version": 1,
            "provenance": {"source": "test"},
        }
        first = client.put(
            f"/v1/sessions/{FIXTURE_SESSION_ID}/annotations/{annotation_id}",
            headers=headers("analyst", "update-1"),
            json=update,
        )
        stale = client.put(
            f"/v1/sessions/{FIXTURE_SESSION_ID}/annotations/{annotation_id}",
            headers=headers("analyst", "update-2"),
            json=update,
        )
        assert first.status_code == 200
        assert first.json()["shape"] == "interval"
        assert stale.status_code == 409
        assert stale.json()["current_version"] == 2
        history = client.get(
            f"/v1/sessions/{FIXTURE_SESSION_ID}/annotations/{annotation_id}/history",
            headers=headers("viewer", "unused"),
        )
        assert [event["action"] for event in history.json()["items"]] == [
            "annotation.created",
            "annotation.updated",
        ]
        assert history.json()["items"][0]["payload"]["snapshot"]["provenance"] == {"source": "test"}


def test_permissions_separate_read_draft_and_review() -> None:
    with TestClient(create_app()) as client:
        denied_draft = client.post(
            f"/v1/sessions/{FIXTURE_SESSION_ID}/annotations",
            headers=headers("viewer", "viewer-create"),
            json={"start_ns": FIXTURE_MANIFEST.start_ns, "kind": "note"},
        )
        assert denied_draft.status_code == 403
        item = create(client)
        denied_review = client.post(
            f"/v1/sessions/{FIXTURE_SESSION_ID}/annotations/{item['id']}/review",
            headers=headers("analyst", "analyst-review"),
            json={"expected_version": 1, "decision": "approved"},
        )
        assert denied_review.status_code == 403
        approved = client.post(
            f"/v1/sessions/{FIXTURE_SESSION_ID}/annotations/{item['id']}/review",
            headers=headers("engineer", "engineer-review"),
            json={"expected_version": 1, "decision": "approved", "comment": "verified"},
        )
        assert approved.status_code == 200
        assert approved.json()["status"] == "approved"
        assert approved.json()["actor"] == "engineer-user"


def test_repository_update_is_atomic_under_concurrency() -> None:
    app = create_app()
    with TestClient(app):
        repository = app.state.annotation_repository
        now = datetime.now(UTC)
        original = Annotation(
            id=uuid4(),
            session_id="fixture-session",
            start_ns=1,
            end_ns=1,
            kind="note",
            actor="a",
            created_at=now,
            updated_at=now,
        )
        asyncio.run(repository.create(original))
        one = original.model_copy(update={"version": 2, "actor": "one"})
        two = original.model_copy(update={"version": 2, "actor": "two"})

        async def race() -> list[Annotation | None]:
            return list(await asyncio.gather(repository.update(one, 1), repository.update(two, 1)))

        results = asyncio.run(race())
        assert sum(result is not None for result in results) == 1
