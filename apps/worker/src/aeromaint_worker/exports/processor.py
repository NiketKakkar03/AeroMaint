import asyncio
import hashlib
import json
import shutil
from collections.abc import Awaitable, Callable, Sequence
from decimal import Decimal
from pathlib import Path
from typing import Any

import pyarrow as pa  # type: ignore[import-untyped]
import pyarrow.ipc as ipc  # type: ignore[import-untyped]

from aeromaint_api.domain.manifest import CaptureSessionManifest, CaptureStream
from aeromaint_api.repositories.models import ExportJob
from aeromaint_api.services.playback import SessionRepository


class ExportCancelled(Exception):
    pass


def _overlaps(start_ns: int, end_ns: int, other_start: int, other_end: int) -> bool:
    return start_ns < other_end and other_start < end_ns


class ExportProcessor:
    """Materializes one synchronized, half-open [start_ns, end_ns) export."""

    def __init__(self, sessions: SessionRepository, root: Path) -> None:
        self.sessions = sessions
        self.root = root

    async def run(
        self,
        job: ExportJob,
        cancelled: Callable[[], Awaitable[bool]],
        annotations: Sequence[dict[str, Any]] = (),
    ) -> dict[str, Any]:
        record = self.sessions.session(job.session_id)
        if record is None:
            raise FileNotFoundError(f"session {job.session_id} not found")
        target = self.root / str(job.id)
        target.mkdir(parents=True, exist_ok=True)
        outputs: list[dict[str, Any]] = []
        disclosures: list[dict[str, Any]] = []
        selected = [s for s in record.manifest.streams if s.id in job.stream_ids]
        for stream in selected:
            if await cancelled():
                raise ExportCancelled
            actual_start = max(job.start_ns, stream.start_ns)
            actual_end = min(job.end_ns, stream.end_ns)
            if actual_start > job.start_ns or actual_end < job.end_ns:
                disclosures.append(
                    {
                        "type": "truncation",
                        "stream_id": stream.id,
                        "requested_start_ns": str(job.start_ns),
                        "requested_end_ns": str(job.end_ns),
                        "actual_start_ns": str(actual_start),
                        "actual_end_ns": str(actual_end),
                    }
                )
            for gap in stream.gaps:
                if _overlaps(job.start_ns, job.end_ns, gap.start_ns, gap.end_ns):
                    disclosures.append(
                        {
                            "type": "gap",
                            "stream_id": stream.id,
                            "start_ns": str(max(job.start_ns, gap.start_ns)),
                            "end_ns": str(min(job.end_ns, gap.end_ns)),
                            "reason": gap.reason,
                        }
                    )
            if stream.kind == "video":
                output = await self._video(record.manifest, stream, job, target, cancelled)
            else:
                output = self._sensors(stream, job, target)
            outputs.append(output)
        if job.include_annotations:
            sliced = [
                a
                for a in annotations
                if _overlaps(job.start_ns, job.end_ns, int(a["start_ns"]), int(a["end_ns"]) + 1)
            ]
            path = target / "annotations.json"
            path.write_text(json.dumps({"items": sliced}, indent=2), encoding="utf-8")
            outputs.append(self._descriptor(path, "application/json", "annotations"))
        manifest = {
            "schema_version": "1.0.0",
            "export_id": str(job.id),
            "session_id": job.session_id,
            "window": {
                "start_ns": str(job.start_ns),
                "end_ns": str(job.end_ns),
                "semantics": "[start_ns,end_ns)",
            },
            "source": record.manifest.provenance.model_dump(mode="json"),
            "requested_by": job.actor,
            "outputs": outputs,
            "disclosures": disclosures,
        }
        path = target / "manifest.json"
        path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        manifest["manifest_artifact"] = self._descriptor(path, "application/json", "manifest")
        return manifest

    async def _video(
        self,
        manifest: CaptureSessionManifest,
        stream: CaptureStream,
        job: ExportJob,
        target: Path,
        cancelled: Callable[[], Awaitable[bool]],
    ) -> dict[str, Any]:
        artifact = next(a for a in manifest.artifacts if a.id in stream.artifact_ids)
        source = Path(artifact.logical_key)
        output = target / f"{stream.id}.mp4"
        start_seconds = Decimal(job.start_ns - manifest.start_ns) / Decimal(1_000_000_000)
        duration_seconds = Decimal(job.end_ns - job.start_ns) / Decimal(1_000_000_000)
        process = await asyncio.create_subprocess_exec(
            "ffmpeg",
            "-nostdin",
            "-y",
            "-ss",
            f"{start_seconds:.9f}",
            "-i",
            str(source),
            "-t",
            f"{duration_seconds:.9f}",
            "-map",
            "0:v:0",
            "-an",
            "-c:v",
            "libx264",
            "-movflags",
            "+faststart",
            str(output),
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        while process.returncode is None:
            try:
                await asyncio.wait_for(process.wait(), timeout=0.05)
            except TimeoutError:
                if await cancelled():
                    process.terminate()
                    await process.wait()
                    raise ExportCancelled from None
        if process.returncode != 0:
            error = ""
            if process.stderr is not None:
                error = (await process.stderr.read()).decode(errors="replace")[-2000:]
            raise RuntimeError(f"ffmpeg failed: {error}")
        return self._descriptor(output, "video/mp4", stream.id)

    def _sensors(self, stream: CaptureStream, job: ExportJob, target: Path) -> dict[str, Any]:
        samples = [
            s
            for s in self.sessions.samples(job.session_id, stream.id)
            if job.start_ns <= s.timestamp_ns < job.end_ns
        ]
        if job.sensor_format == "json":
            path = target / f"{stream.id}.json"
            path.write_text(
                json.dumps(
                    {
                        "stream_id": stream.id,
                        "samples": [
                            {"timestamp_ns": str(s.timestamp_ns), **s.values} for s in samples
                        ],
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
            return self._descriptor(path, "application/json", stream.id, len(samples))
        fields = sorted({key for sample in samples for key in sample.values})
        columns: dict[str, Any] = {
            "timestamp_ns": pa.array([s.timestamp_ns for s in samples], type=pa.int64())
        }
        for field in fields:
            columns[field] = pa.array([s.values.get(field) for s in samples])
        table = pa.table(columns)
        path = target / f"{stream.id}.arrow"
        with path.open("wb") as sink, ipc.new_stream(sink, table.schema) as writer:
            writer.write_table(table)
        return self._descriptor(
            path, "application/vnd.apache.arrow.stream", stream.id, len(samples)
        )

    @staticmethod
    def _descriptor(
        path: Path, media_type: str, stream_id: str, count: int | None = None
    ) -> dict[str, Any]:
        data = path.read_bytes()
        result: dict[str, Any] = {
            "stream_id": stream_id,
            "file": path.name,
            "media_type": media_type,
            "size_bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
        }
        if count is not None:
            result["sample_count"] = count
        return result

    @staticmethod
    def remove_partial(root: Path, export_id: str) -> None:
        shutil.rmtree(root / export_id, ignore_errors=True)
