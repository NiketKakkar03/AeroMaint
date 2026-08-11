"""Build reproducible wheel and sdist artifacts using only the Python standard library."""

from __future__ import annotations

import base64
import csv
import hashlib
import io
import sys
import tarfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
NAME = "aeromaint_capture_sdk"
VERSION = "1.0.0"
DIST_INFO = f"{NAME}-{VERSION}.dist-info"
METADATA = f"""Metadata-Version: 2.1
Name: aeromaint-capture-sdk
Version: {VERSION}
Summary: Typed Python client for the AeroMaint capture API
Requires-Python: >=3.11
License: MIT
"""


def digest(data: bytes) -> tuple[str, str]:
    value = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode()
    return f"sha256={value}", str(len(data))


def build(out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    sources = sorted((ROOT / "src" / "aeromaint_capture").glob("*"))
    wheel_files: dict[str, bytes] = {
        f"aeromaint_capture/{path.name}": path.read_bytes() for path in sources if path.is_file()
    }
    wheel_files[f"{DIST_INFO}/METADATA"] = METADATA.encode()
    wheel_files[f"{DIST_INFO}/WHEEL"] = (
        b"Wheel-Version: 1.0\n"
        b"Generator: aeromaint-stdlib-builder\n"
        b"Root-Is-Purelib: true\n"
        b"Tag: py3-none-any\n"
    )
    records = [[name, *digest(data)] for name, data in wheel_files.items()]
    records.append([f"{DIST_INFO}/RECORD", "", ""])
    record = io.StringIO()
    csv.writer(record, lineterminator="\n").writerows(records)
    wheel_files[f"{DIST_INFO}/RECORD"] = record.getvalue().encode()
    with zipfile.ZipFile(
        out / f"{NAME}-{VERSION}-py3-none-any.whl", "w", zipfile.ZIP_DEFLATED
    ) as archive:
        for name, data in wheel_files.items():
            info = zipfile.ZipInfo(name, (2020, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, data)

    prefix = f"aeromaint_capture_sdk-{VERSION}"
    with tarfile.open(out / f"{prefix}.tar.gz", "w:gz", format=tarfile.PAX_FORMAT) as archive:
        for path in [
            ROOT / "pyproject.toml",
            ROOT / "README.md",
            ROOT / "build_artifacts.py",
            *sources,
        ]:
            archive.add(path, arcname=f"{prefix}/{path.relative_to(ROOT)}")


if __name__ == "__main__":
    build(Path(sys.argv[1] if len(sys.argv) > 1 else ROOT / "dist"))
