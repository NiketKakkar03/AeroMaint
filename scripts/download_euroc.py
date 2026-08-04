"""Explicit, checksum-gated EuRoC acquisition.

The EuRoC publisher does not provide SHA-256 values with the legacy per-sequence
downloads. Callers must therefore supply a digest obtained from a trusted copy or
an organization-owned acquisition record. A download is never extracted before
the supplied digest matches.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

SEQUENCES = {
    "V1_01_easy": (
        "https://robotics.ethz.ch/~asl-datasets/ijrr_euroc_mav_dataset/"
        "vicon_room1/V1_01_easy/V1_01_easy.zip"
    ),
    "MH_01_easy": (
        "https://robotics.ethz.ch/~asl-datasets/ijrr_euroc_mav_dataset/"
        "machine_hall/MH_01_easy/MH_01_easy.zip"
    ),
}


class AcquisitionError(RuntimeError):
    """An acquisition or verification operation failed safely."""


def validate_digest(value: str) -> str:
    digest = value.lower()
    if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
        raise AcquisitionError("expected SHA-256 must be 64 hexadecimal characters")
    return digest


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify(path: Path, expected: str) -> str:
    expected = validate_digest(expected)
    actual = sha256_file(path)
    if actual != expected:
        raise AcquisitionError(f"SHA-256 mismatch for {path}: expected {expected}, got {actual}")
    return actual


def safe_extract(archive: Path, destination: Path) -> None:
    destination = destination.resolve()
    with zipfile.ZipFile(archive) as source:
        for member in source.infolist():
            target = (destination / member.filename).resolve()
            if destination != target and destination not in target.parents:
                raise AcquisitionError(f"archive contains unsafe path: {member.filename}")
        source.extractall(destination)


def download(sequence: str, destination: Path, expected: str) -> Path:
    url = SEQUENCES[sequence]
    destination.mkdir(parents=True, exist_ok=True)
    final_directory = destination / sequence
    if final_directory.exists():
        raise AcquisitionError(f"destination already exists: {final_directory}")

    with tempfile.TemporaryDirectory(prefix="aeromaint-euroc-") as temporary:
        temporary_path = Path(temporary)
        archive = temporary_path / f"{sequence}.zip"
        with urllib.request.urlopen(url) as response, archive.open("wb") as output:  # noqa: S310
            shutil.copyfileobj(response, output)
        digest = verify(archive, expected)
        extracted = temporary_path / "extracted"
        extracted.mkdir()
        safe_extract(archive, extracted)
        source_root = extracted / "mav0"
        if not source_root.is_dir():
            raise AcquisitionError("verified archive does not contain the expected mav0 directory")
        shutil.move(str(source_root), final_directory)
        record = {
            "sequence": sequence,
            "source_url": url,
            "source_sha256": digest,
            "archive_size_bytes": archive.stat().st_size,
        }
        (final_directory / "AEROMAINT_ACQUISITION.json").write_text(
            json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    return final_directory


def verify_fixture(root: Path) -> None:
    sums = root / "SHA256SUMS"
    if not sums.is_file():
        raise AcquisitionError(f"missing fixture checksum file: {sums}")
    for line in sums.read_text(encoding="utf-8").splitlines():
        if not line:
            continue
        digest, relative = line.split("  ", 1)
        verify(root / relative, digest)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    commands = result.add_subparsers(dest="command", required=True)
    acquire = commands.add_parser("download")
    acquire.add_argument("--sequence", choices=sorted(SEQUENCES), required=True)
    acquire.add_argument("--destination", type=Path, required=True)
    acquire.add_argument("--sha256", required=True)
    check = commands.add_parser("verify")
    check.add_argument("--archive", type=Path, required=True)
    check.add_argument("--sha256", required=True)
    fixture = commands.add_parser("verify-fixture")
    fixture.add_argument("root", type=Path)
    return result


def main() -> int:
    arguments = parser().parse_args()
    try:
        if arguments.command == "download":
            path = download(arguments.sequence, arguments.destination, arguments.sha256)
            print(f"verified and extracted {arguments.sequence} to {path}")
        elif arguments.command == "verify":
            print(verify(arguments.archive, arguments.sha256))
        else:
            verify_fixture(arguments.root)
            print(f"fixture checksums verified: {arguments.root}")
    except (AcquisitionError, OSError, zipfile.BadZipFile) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
