import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest

from aeromaint_api.domain.fixtures import FIXTURE_MANIFEST, FIXTURE_SESSION_ID
from aeromaint_api.repositories.models import ExportJob
from aeromaint_api.services.playback import InMemorySessionRepository
from aeromaint_worker.exports import ExportCancelled, ExportProcessor


def job(start_ns: int, end_ns: int, streams: list[str]) -> ExportJob:
    now = datetime.now(UTC)
    return ExportJob(
        id=uuid4(),
        idempotency_key="key",
        session_id=FIXTURE_SESSION_ID,
        actor="test",
        start_ns=start_ns,
        end_ns=end_ns,
        stream_ids=streams,
        include_annotations=False,
        created_at=now,
        updated_at=now,
        expires_at=now + timedelta(days=1),
    )


@pytest.mark.asyncio
async def test_ffmpeg_clip_uses_exact_nanosecond_offsets(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    seen: tuple[str, ...] = ()

    class Process:
        returncode: int | None = None
        stderr = None

        async def wait(self) -> int:
            self.returncode = 0
            return 0

        def terminate(self) -> None:
            self.returncode = -15

    async def spawn(*args: str, **_kwargs: object) -> Process:
        nonlocal seen
        seen = args
        Path(args[-1]).write_bytes(b"fixture-mp4")  # noqa: ASYNC240 - subprocess test double
        return Process()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn)
    start = FIXTURE_MANIFEST.start_ns + 1_234_567_890
    item = job(start, start + 2_000_000_001, ["camera-left"])
    manifest = FIXTURE_MANIFEST
    stream = next(value for value in manifest.streams if value.id == "camera-left")
    result = await ExportProcessor(InMemorySessionRepository(), tmp_path)._video(
        manifest, stream, item, tmp_path, lambda: asyncio.sleep(0, result=False)
    )
    assert seen[0] == "ffmpeg"
    assert seen[seen.index("-ss") + 1] == "1.234567890"
    assert seen[seen.index("-t") + 1] == "2.000000001"
    assert result["sha256"]


@pytest.mark.asyncio
async def test_processor_honors_cancellation_before_materializing(tmp_path: Path) -> None:
    start = FIXTURE_MANIFEST.start_ns
    processor = ExportProcessor(InMemorySessionRepository(), tmp_path)
    with pytest.raises(ExportCancelled):
        await processor.run(
            job(start, start + 5_000_000, ["imu-main"]),
            lambda: asyncio.sleep(0, result=True),
        )
