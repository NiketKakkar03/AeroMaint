from __future__ import annotations

import hashlib
import json
import shutil
import zipfile
from pathlib import Path

import pyarrow.parquet as pq
import pytest
from packages.features.cmapss import CmapssPreprocessor
from packages.telemetry.cmapss import CMAPSS_COLUMNS, CmapssError, acquire_fd001, parse_fd001
from pipelines.training.data.cmapss import prepare_fd001


def _row(engine: int, cycle: int, *, offset: float = 0, missing_sensor: int | None = None) -> str:
    settings = [offset + cycle / 10, 0.0, 100.0]
    sensors = [offset + cycle + index for index in range(1, 22)]
    if missing_sensor is not None:
        sensors[missing_sensor - 1] = float("nan")
    return " ".join(str(value) for value in [engine, cycle, *settings, *sensors])


def _fixture(path: Path, engines: int = 8) -> Path:
    path.write_text(
        "\n".join(
            _row(engine, cycle, offset=engine * 10, missing_sensor=2 if cycle == 2 else None)
            for engine in range(1, engines + 1)
            for cycle in range(1, 5)
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def test_parser_schema_and_missing_values(tmp_path: Path) -> None:
    parsed = parse_fd001(_fixture(tmp_path / "train_FD001.txt", engines=1))
    assert tuple(parsed.rows[0]) == CMAPSS_COLUMNS
    assert parsed.rows[1]["sensor_2"] is None
    assert parsed.engine_ids == (1,)


def test_parser_rejects_bad_schema_and_cycle_order(tmp_path: Path) -> None:
    malformed = tmp_path / "bad.txt"
    malformed.write_text("1 1 2\n", encoding="utf-8")
    with pytest.raises(CmapssError, match="expected 26 columns"):
        parse_fd001(malformed)
    malformed.write_text(_row(1, 2) + "\n" + _row(1, 1) + "\n", encoding="utf-8")
    with pytest.raises(CmapssError, match="cycles must increase"):
        parse_fd001(malformed)


def test_acquisition_is_optional_checksum_verified_and_path_safe(tmp_path: Path) -> None:
    archive = tmp_path / "source.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("CMAPSSData/train_FD001.txt", _row(1, 1))
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()

    def copy(_url: str, target: str) -> object:
        return shutil.copyfile(archive, target)

    result = acquire_fd001("fixture://fd001", tmp_path / "raw.txt", digest, opener=copy)
    assert result.read_text(encoding="utf-8") == _row(1, 1)
    with pytest.raises(CmapssError, match="SHA-256 mismatch"):
        acquire_fd001("fixture://fd001", tmp_path / "rejected.txt", "0" * 64, opener=copy)


def test_fit_uses_training_rows_and_explicit_sensor_policies() -> None:
    rows = [
        dict(zip(CMAPSS_COLUMNS, [1, cycle, cycle, 0.0, 1.0, *([float(cycle)] * 21)], strict=True))
        for cycle in (1, 2)
    ]
    transform = CmapssPreprocessor.fit(rows)
    assert transform.fit_engine_ids == (1,)
    assert "setting_2" in transform.constant_features
    assert "setting_2" not in transform.active_features
    assert transform.missing_policy == "median"
    assert transform.constant_policy == "drop"


def test_pipeline_enforces_isolation_versions_and_determinism(tmp_path: Path) -> None:
    source = _fixture(tmp_path / "train_FD001.txt")
    first = prepare_fd001(source, tmp_path / "prepared-a", rul_cap=2)
    second = prepare_fd001(source, tmp_path / "prepared-b", rul_cap=2)
    groups = [set(engine_ids) for engine_ids in first.split_engine_ids.values()]
    assert all(
        not left.intersection(right)
        for index, left in enumerate(groups)
        for right in groups[index + 1 :]
    )
    assert set.union(*groups) == set(range(1, 9))
    assert first.data_version == second.data_version
    assert first.feature_version == second.feature_version
    assert first.feature_checksum == second.feature_checksum

    manifest = json.loads((first.path / "manifest.json").read_text(encoding="utf-8"))
    transform = json.loads((first.path / "transform.json").read_text(encoding="utf-8"))
    assert set(transform["fit_engine_ids"]) == set(first.split_engine_ids["train"])
    assert manifest["source_sha256"] == hashlib.sha256(source.read_bytes()).hexdigest()
    assert manifest["feature_checksum"] == first.feature_checksum
    assert manifest["rul_cap"] == 2

    for split, engine_ids in first.split_engine_ids.items():
        table = pq.read_table(first.path / f"{split}.parquet")
        assert set(table.column("engine_id").to_pylist()) == set(engine_ids)
        assert max(table.column("rul").to_pylist()) <= 2
        assert table.schema.metadata[b"aeromaint.feature_version"].decode() == first.feature_version
