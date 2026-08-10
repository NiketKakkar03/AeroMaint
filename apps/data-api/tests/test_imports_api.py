from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from aeromaint_api.api.v1.imports import get_import_repository
from aeromaint_api.main import app
from aeromaint_api.repositories import ImportJob, ImportStatus


class FakeImportRepository:
    def __init__(self) -> None:
        self.job: ImportJob | None = None

    async def create(self, idempotency_key: str, source_uri: str) -> tuple[ImportJob, bool]:
        if self.job is not None:
            return self.job, False
        now = datetime.now(UTC)
        self.job = ImportJob(
            id=uuid4(),
            idempotency_key=idempotency_key,
            source_uri=source_uri,
            status=ImportStatus.PENDING,
            created_at=now,
            updated_at=now,
        )
        return self.job, True

    async def get(self, import_id: UUID) -> ImportJob | None:
        return self.job if self.job is not None and self.job.id == import_id else None


def test_import_creation_is_idempotent_and_status_is_exposed() -> None:
    repository = FakeImportRepository()
    app.dependency_overrides[get_import_repository] = lambda: repository
    try:
        with TestClient(app) as client:
            first = client.post(
                "/v1/imports",
                headers={"Idempotency-Key": "upload-1"},
                json={"source_uri": "file:///capture"},
            )
            second = client.post(
                "/v1/imports",
                headers={"Idempotency-Key": "upload-1"},
                json={"source_uri": "file:///capture"},
            )
            fetched = client.get(f"/v1/imports/{first.json()['id']}")
    finally:
        app.dependency_overrides.clear()

    assert first.status_code == 201
    assert second.status_code == 200
    assert second.json()["id"] == first.json()["id"]
    assert fetched.json()["status"] == "pending"


def test_import_requires_idempotency_key() -> None:
    app.dependency_overrides[get_import_repository] = lambda: FakeImportRepository()
    try:
        response = TestClient(app).post("/v1/imports", json={"source_uri": "file:///capture"})
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 422
