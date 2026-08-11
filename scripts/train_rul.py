from __future__ import annotations

import argparse
from pathlib import Path

from pipelines.training.rul import train_experiment


def main() -> None:
    parser = argparse.ArgumentParser(description="Train and evaluate deterministic FD001 RUL model")
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = train_experiment(args.dataset, args.output)
    print(f"test RMSE: {report['test']['selected']['overall']['rmse']:.6f}")


if __name__ == "__main__":
    main()
