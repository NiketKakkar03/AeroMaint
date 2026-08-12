from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import tarfile
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GIT = shutil.which("git")
REQUIRED = (
    "CHANGELOG.md",
    "docs/architecture.md",
    "docs/dataset_card.md",
    "docs/demo/README.md",
    "docs/limitations.md",
    "docs/migration-guide.md",
    "docs/model_card.md",
    "docs/release-notes.md",
    "docs/runbook.md",
    "docs/threat_model.md",
    "evals/reports/README.md",
    "evals/reports/evidence.json",
)
LINK = re.compile(r"(?<!!)\[[^]]+\]\(([^)]+)\)")


def _git(*args: str) -> str:
    if GIT is None:
        raise SystemExit("git is required")
    return subprocess.check_output((GIT, *args), cwd=ROOT, text=True).strip()  # noqa: S603


def audit() -> None:
    errors: list[str] = []
    for relative in REQUIRED:
        if not (ROOT / relative).is_file():
            errors.append(f"missing required file: {relative}")

    for path in sorted(ROOT.rglob("*.md")):
        if any(part in {"node_modules", ".venv"} for part in path.parts):
            continue
        body = path.read_text(encoding="utf-8")
        for target in LINK.findall(body):
            clean = target.split("#", 1)[0]
            if not clean or clean.startswith(("http://", "https://", "mailto:")):
                continue
            if not (path.parent / clean).resolve().exists():
                errors.append(f"broken link: {path.relative_to(ROOT)} -> {target}")

    evidence_path = ROOT / "evals/reports/evidence.json"
    if evidence_path.is_file():
        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
        allowed = {"measured", "fixture_only", "not_run"}
        ids: set[str] = set()
        for entry in evidence.get("entries", []):
            item_id = entry.get("id")
            if not item_id or item_id in ids:
                errors.append(f"duplicate or missing evidence id: {item_id!r}")
            ids.add(item_id)
            if entry.get("status") not in allowed:
                errors.append(f"invalid evidence status for {item_id}")
            report = entry.get("report")
            if report and not (ROOT / report).is_file():
                errors.append(f"missing evidence report for {item_id}: {report}")
            if entry.get("status") != "not_run" and not entry.get("command"):
                errors.append(f"measured evidence lacks command: {item_id}")

    if errors:
        raise SystemExit("release audit failed:\n- " + "\n- ".join(errors))
    print(f"release audit passed: {len(REQUIRED)} required files; local Markdown links valid")


def archive() -> None:
    audit()
    if _git("status", "--porcelain"):
        raise SystemExit("release archive requires a clean committed worktree")
    commit = _git("rev-parse", "HEAD")
    short = commit[:12]
    output = ROOT / "dist/release"
    output.mkdir(parents=True, exist_ok=True)
    archive_path = output / f"aeromaint-{short}.tar.gz"
    if GIT is None:
        raise SystemExit("git is required")
    with tempfile.TemporaryDirectory() as temporary:
        tar_path = Path(temporary) / "source.tar"
        subprocess.run(  # noqa: S603
            (GIT, "archive", f"--prefix=aeromaint-{short}/", "-o", str(tar_path), commit),
            cwd=ROOT,
            check=True,
        )
        with tarfile.open(archive_path, "w:gz", format=tarfile.PAX_FORMAT) as destination:
            with tarfile.open(tar_path, "r:") as source:
                for member in source.getmembers():
                    extracted = source.extractfile(member) if member.isfile() else None
                    destination.addfile(member, extracted)
    digest = hashlib.sha256(archive_path.read_bytes()).hexdigest()
    checksum_path = archive_path.with_suffix(archive_path.suffix + ".sha256")
    checksum_path.write_text(f"{digest}  {archive_path.name}\n", encoding="utf-8")
    manifest = {
        "schema": "aeromaint.release-archive/v1",
        "source_commit": commit,
        "archive": archive_path.name,
        "sha256": digest,
        "source_date_epoch": int(_git("show", "-s", "--format=%ct", commit)),
    }
    (output / f"aeromaint-{short}.manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"created {archive_path.relative_to(ROOT)} ({digest})")


def main() -> None:
    os.chdir(ROOT)
    parser = argparse.ArgumentParser(description="Audit or package an AeroMaint source release")
    parser.add_argument("command", choices=("audit", "archive"))
    args = parser.parse_args()
    audit() if args.command == "audit" else archive()


if __name__ == "__main__":
    main()
