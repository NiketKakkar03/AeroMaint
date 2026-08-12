"""Build SDK artifacts and a checksummed, versioned local release manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def command(args: list[str], env: dict[str, str]) -> None:
    subprocess.run(args, cwd=ROOT, env=env, check=True)  # noqa: S603


def package_version(path: Path) -> str:
    return str(json.loads(path.read_text())["version"])


def build(output: Path) -> dict[str, Any]:
    output.mkdir(parents=True, exist_ok=True)
    environment = {
        **os.environ,
        "AEROMAINT_RELEASE_OUTPUT": str(output.resolve()),
        "PATH": f"{ROOT / 'node_modules/.bin'}{os.pathsep}{os.environ.get('PATH', '')}",
    }
    command(["node", "tests/contract/sdk-ts/run-packed-smoke.mjs"], environment)
    command(["sh", "tests/contract/sdk-python/run-packed-smoke.sh"], environment)
    git = shutil.which("git")
    if git is None:
        raise RuntimeError("git is required to identify the release source commit")
    commit = subprocess.run(  # noqa: S603 - resolved git executable with fixed arguments
        [git, "rev-parse", "HEAD"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    artifacts = [
        {
            "name": path.name,
            "bytes": path.stat().st_size,
            "sha256": sha256(path),
        }
        for path in sorted(output.iterdir())
        if path.is_file() and path.name not in {"SHA256SUMS", "release-manifest.json"}
    ]
    manifest: dict[str, Any] = {
        "schema_version": "1.0.0",
        "release_version": package_version(ROOT / "package.json"),
        "source_commit": commit,
        "components": {
            "typescript_sdk": package_version(ROOT / "packages/capture-sdk-ts/package.json"),
            "python_sdk": "1.0.0",
            "api": "0.1.0",
            "viewer": package_version(ROOT / "apps/viewer/package.json"),
        },
        "artifacts": artifacts,
    }
    (output / "release-manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    )
    checksum_paths = [*sorted(output.iterdir()), output / "release-manifest.json"]
    unique_paths = {path.resolve(): path for path in checksum_paths if path.name != "SHA256SUMS"}
    (output / "SHA256SUMS").write_text(
        "".join(f"{sha256(path)}  {path.name}\n" for path in unique_paths.values())
    )
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts/release")
    args = parser.parse_args()
    manifest = build(args.output)
    print(f"built {len(manifest['artifacts'])} checksummed release artifacts in {args.output}")


if __name__ == "__main__":
    main()
