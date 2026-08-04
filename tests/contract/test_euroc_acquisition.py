import zipfile
from pathlib import Path

import pytest
import scripts.download_euroc as acquisition
from scripts.download_euroc import AcquisitionError, sha256_file, verify, verify_fixture

FIXTURE = Path("tests/media-fixtures/euroc-mini")


def test_fixture_is_redistribution_safe_and_checksum_verified() -> None:
    verify_fixture(FIXTURE)
    notice = (FIXTURE / "README.md").read_text(encoding="utf-8")
    assert "authored for AeroMaint CI" in notice
    assert "not copied or derived from the EuRoC dataset" in " ".join(notice.split())


def test_checksum_rejects_corrupt_input(tmp_path: Path) -> None:
    archive = tmp_path / "sample.zip"
    archive.write_bytes(b"known acquisition")
    expected = sha256_file(archive)
    verify(archive, expected)

    archive.write_bytes(b"corrupt acquisition")
    with pytest.raises(AcquisitionError, match="SHA-256 mismatch"):
        verify(archive, expected)


def test_download_verifies_and_extracts_in_fresh_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    archive = tmp_path / "source.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("mav0/cam0/data.csv", "# synthetic\n")
    monkeypatch.setitem(acquisition.SEQUENCES, "V1_01_easy", archive.as_uri())

    destination = tmp_path / "fresh" / "data"
    extracted = acquisition.download("V1_01_easy", destination, sha256_file(archive))

    assert (extracted / "cam0" / "data.csv").read_text(encoding="utf-8") == "# synthetic\n"
    assert (extracted / "AEROMAINT_ACQUISITION.json").is_file()


@pytest.mark.parametrize("digest", ["", "xyz", "0" * 63, "G" * 64])
def test_checksum_rejects_malformed_expected_digest(tmp_path: Path, digest: str) -> None:
    archive = tmp_path / "sample.zip"
    archive.write_bytes(b"sample")
    with pytest.raises(AcquisitionError, match="64 hexadecimal"):
        verify(archive, digest)
