"""EuRoC worker command using the shared canonical pipeline."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from pipelines.ingestion import ingest_euroc


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--source-uri", required=True)
    arguments = parser.parse_args()
    result = ingest_euroc(arguments.source, arguments.output, arguments.source_uri)
    print(
        json.dumps(
            {
                "artifact_count": result.artifact_count,
                "gap_count": result.gap_count,
                "manifest_path": str(result.manifest_path),
                "reused": result.reused,
                "session_id": result.session_id,
                "source_sha256": result.source_sha256,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
