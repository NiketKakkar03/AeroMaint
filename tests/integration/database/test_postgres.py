import asyncio
import json
import os
from pathlib import Path

import pytest
import pytest_asyncio
from psycopg.errors import ObjectNotInPrerequisiteState

from aeromaint_api.db import Database, MigrationRunner
from aeromaint_api.domain.manifest import CaptureSessionManifest
from aeromaint_api.repositories import (
    PostgresAuditRepository,
    PostgresImportRepository,
    PostgresSessionRepository,
)

DATABASE_URL = os.getenv("AEROMAINT_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    DATABASE_URL is None, reason="AEROMAINT_TEST_DATABASE_URL is not set"
)
FIXTURE = Path(__file__).parents[2] / "contract" / "fixtures" / "capture-manifest-v1.json"


@pytest_asyncio.fixture
async def database() -> Database:
    assert DATABASE_URL is not None
    database = Database(DATABASE_URL)
    runner = MigrationRunner(database)
    await runner.downgrade()
    await runner.upgrade()
    yield database
    await runner.downgrade()


@pytest.mark.asyncio
async def test_empty_database_migrates_and_rolls_back(database: Database) -> None:
    async with database.connection() as connection:
        cursor = await connection.execute("SELECT to_regclass('sessions') AS name")
        assert (await cursor.fetchone())["name"] == "sessions"
    await MigrationRunner(database).downgrade()
    async with database.connection() as connection:
        cursor = await connection.execute("SELECT to_regclass('sessions') AS name")
        assert (await cursor.fetchone())["name"] is None


@pytest.mark.asyncio
async def test_manifest_persists_as_metadata_and_artifact_pointers(database: Database) -> None:
    manifest = CaptureSessionManifest.model_validate(json.loads(FIXTURE.read_text()))
    repository = PostgresSessionRepository(database)
    await repository.put(manifest)
    assert await repository.get(manifest.session_id) == manifest
    async with database.connection() as connection:
        cursor = await connection.execute(
            "SELECT logical_key, size_bytes, sha256 FROM artifacts WHERE session_id=%s",
            (manifest.session_id,),
        )
        rows = await cursor.fetchall()
    assert rows and all(set(row) == {"logical_key", "size_bytes", "sha256"} for row in rows)


@pytest.mark.asyncio
async def test_concurrent_import_creation_has_one_identity(database: Database) -> None:
    repository = PostgresImportRepository(database)
    results = await asyncio.gather(
        *(repository.create("same-upload", "file:///capture") for _ in range(8))
    )
    assert len({job.id for job, _created in results}) == 1
    assert sum(created for _job, created in results) == 1


@pytest.mark.asyncio
async def test_audit_events_are_append_only(database: Database) -> None:
    repository = PostgresAuditRepository(database)
    event = await repository.append("tester", "created", "session", "s1", {"source": "test"})
    with pytest.raises(ObjectNotInPrerequisiteState, match="append-only"):
        async with database.connection() as connection, connection.transaction():
            await connection.execute("DELETE FROM audit_events WHERE id=%s", (event.id,))
    assert [item.id for item in await repository.list_for_entity("session", "s1")] == [event.id]
