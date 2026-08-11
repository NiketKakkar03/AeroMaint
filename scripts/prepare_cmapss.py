#!/usr/bin/env python3
"""Prepare or acquire the C-MAPSS FD001 dataset."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from packages.telemetry.cmapss import acquire_fd001
from pipelines.training.data.cmapss import prepare_fd001


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subcommands = parser.add_subparsers(dest="command", required=True)
    acquire = subcommands.add_parser("acquire")
    acquire.add_argument("--url", required=True)
    acquire.add_argument("--sha256", required=True)
    acquire.add_argument("--output", type=Path, required=True)
    prepare = subcommands.add_parser("prepare")
    prepare.add_argument("--source", type=Path, required=True)
    prepare.add_argument("--destination", type=Path, required=True)
    prepare.add_argument("--rul-cap", type=int, default=125)
    prepare.add_argument("--split-seed", default="aeromaint-fd001-v1")
    args = parser.parse_args()
    if args.command == "acquire":
        print(acquire_fd001(args.url, args.output, args.sha256))
    else:
        result = prepare_fd001(
            args.source,
            args.destination,
            rul_cap=args.rul_cap,
            split_seed=args.split_seed,
        )
        print(
            json.dumps(
                {
                    "path": str(result.path),
                    "data_version": result.data_version,
                    "feature_version": result.feature_version,
                    "feature_checksum": result.feature_checksum,
                },
                sort_keys=True,
            )
        )


if __name__ == "__main__":
    main()
