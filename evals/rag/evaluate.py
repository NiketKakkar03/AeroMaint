"""Run the curated, deterministic top-k retrieval gate."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from packages.retrieval import HybridIndex


def evaluate(
    index: HybridIndex, queries: list[dict[str, object]], *, target: float = 0.8
) -> dict[str, object]:
    relevant = 0
    details: list[dict[str, object]] = []
    for case in queries:
        result = index.search(str(case["query"]), limit=5)
        titles = [item["citation"]["title"] for item in result.results]
        passed = case.get("expected_status", "ok") == result.status
        if "expected_title" in case:
            passed = passed and case["expected_title"] in titles
        relevant += passed
        details.append(
            {"query": case["query"], "passed": passed, "status": result.status, "titles": titles}
        )
    score = relevant / len(queries) if queries else 0.0
    return {
        "top_5_relevance": score,
        "target": target,
        "passed": score >= target,
        "queries": details,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--index", type=Path, required=True)
    parser.add_argument("--queries", type=Path, default=Path("evals/rag/queries.json"))
    arguments = parser.parse_args()
    print(
        json.dumps(
            evaluate(HybridIndex.read(arguments.index), json.loads(arguments.queries.read_text())),
            indent=2,
        )
    )
