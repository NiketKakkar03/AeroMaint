"""Create reproducible, engine-isolated FD001 artifacts."""

from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import pyarrow as pa  # type: ignore[import-untyped]
import pyarrow.parquet as pq  # type: ignore[import-untyped]
from packages.features.cmapss import CmapssPreprocessor
from packages.telemetry.cmapss import parse_fd001

DATASET_FORMAT_VERSION = "aeromaint.cmapss-fd001/v1"


@dataclass(frozen=True)
class PreparedDataset:
    path: Path
    data_version: str
    feature_version: str
    feature_checksum: str
    split_engine_ids: dict[str, tuple[int, ...]]


def _canonical(value: Any) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n"
    ).encode()


def split_engines(
    engine_ids: tuple[int, ...],
    *,
    seed: str = "aeromaint-fd001-v1",
    validation: float = 0.2,
    test: float = 0.2,
) -> dict[str, tuple[int, ...]]:
    if not engine_ids or validation < 0 or test < 0 or validation + test >= 1:
        raise ValueError("engine IDs and split fractions must define a non-empty training split")
    unique = sorted(
        set(engine_ids), key=lambda value: hashlib.sha256(f"{seed}:{value}".encode()).digest()
    )
    count = len(unique)
    validation_count = round(count * validation)
    test_count = round(count * test)
    if validation and count >= 3:
        validation_count = max(1, validation_count)
    if test and count >= 3:
        test_count = max(1, test_count)
    while validation_count + test_count >= count:
        if test_count >= validation_count and test_count:
            test_count -= 1
        else:
            validation_count -= 1
    return {
        "train": tuple(sorted(unique[validation_count + test_count :])),
        "validation": tuple(sorted(unique[:validation_count])),
        "test": tuple(sorted(unique[validation_count : validation_count + test_count])),
    }


def _write_parquet(path: Path, rows: list[dict[str, Any]], metadata: dict[str, str]) -> None:
    table = pa.Table.from_pylist(rows)
    table = table.replace_schema_metadata(
        {key.encode(): value.encode() for key, value in metadata.items()}
    )
    pq.write_table(table, path, compression="zstd", use_dictionary=False, write_statistics=True)


def prepare_fd001(
    source: Path,
    destination: Path,
    *,
    rul_cap: int = 125,
    split_seed: str = "aeromaint-fd001-v1",
    validation_fraction: float = 0.2,
    test_fraction: float = 0.2,
) -> PreparedDataset:
    """Build and atomically publish versioned raw, transform, and feature artifacts."""
    if rul_cap < 1:
        raise ValueError("rul_cap must be positive")
    parsed = parse_fd001(source)
    splits = split_engines(
        parsed.engine_ids, seed=split_seed, validation=validation_fraction, test=test_fraction
    )
    owner = {engine_id: split for split, ids in splits.items() for engine_id in ids}
    if len(owner) != len(parsed.engine_ids):
        raise RuntimeError("engine split isolation invariant failed")
    rows_by_split = {
        split: [row for row in parsed.rows if owner[cast(int, row["engine_id"])] == split]
        for split in ("train", "validation", "test")
    }
    preprocessor = CmapssPreprocessor.fit(rows_by_split["train"])
    transformed = {
        split: preprocessor.transform(rows, split, rul_cap) for split, rows in rows_by_split.items()
    }
    transform_bytes = _canonical(preprocessor.to_dict())
    transform_sha256 = hashlib.sha256(transform_bytes).hexdigest()
    feature_checksum = hashlib.sha256(
        "".join(transformed[split].checksum for split in ("train", "validation", "test")).encode()
    ).hexdigest()
    config = {
        "format_version": DATASET_FORMAT_VERSION,
        "source_sha256": parsed.source_sha256,
        "rul_cap": rul_cap,
        "split_seed": split_seed,
        "validation_fraction": validation_fraction,
        "test_fraction": test_fraction,
        "splits": {key: list(value) for key, value in splits.items()},
        "transform_sha256": transform_sha256,
        "feature_checksum": feature_checksum,
    }
    data_version = hashlib.sha256(_canonical(config)).hexdigest()
    feature_version = f"{preprocessor.version}+sha256.{transform_sha256[:12]}"
    manifest = {
        **config,
        "data_version": f"sha256:{data_version}",
        "feature_version": feature_version,
        "missing_sensor_policy": (
            "training median imputation; entirely-missing training features reject"
        ),
        "constant_sensor_policy": "drop when variance is zero in training data",
        "artifacts": [
            "raw.parquet",
            "train.parquet",
            "validation.parquet",
            "test.parquet",
            "transform.json",
        ],
    }
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{destination.name}-", dir=destination.parent))
    try:
        metadata = {
            "aeromaint.dataset_format_version": DATASET_FORMAT_VERSION,
            "aeromaint.data_version": data_version,
            "aeromaint.feature_version": feature_version,
            "aeromaint.source_sha256": parsed.source_sha256,
        }
        _write_parquet(temporary / "raw.parquet", list(parsed.rows), metadata)
        for split, result in transformed.items():
            _write_parquet(temporary / f"{split}.parquet", list(result.rows), metadata)
        (temporary / "transform.json").write_bytes(transform_bytes)
        (temporary / "manifest.json").write_bytes(_canonical(manifest))
        if destination.exists():
            raise FileExistsError(f"refusing to overwrite dataset: {destination}")
        temporary.rename(destination)
    except BaseException:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return PreparedDataset(destination, data_version, feature_version, feature_checksum, splits)
