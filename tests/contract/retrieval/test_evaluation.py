import json
from pathlib import Path

from evals.rag.evaluate import evaluate
from packages.retrieval import Document, build_index


def test_curated_top_five_gate_and_abstention() -> None:
    index = build_index(
        [
            Document(
                "https://ntrs.nasa.gov/citations/20090029214",
                "NASA C-MAPSS turbofan degradation simulation",
                "2008",
                "# Prognostics\nC-MAPSS simulates turbofan engine degradation trajectories. "
                "Remaining useful life labels describe simulated cycles.",
            ),
            Document(
                "https://www.faa.gov/documentLibrary/ac-43-13",
                "FAA AC 43.13-1B",
                "Change 1",
                "# Approval\nReturn to service requires authorized maintenance approval "
                "using approved data.",
            ),
        ]
    )
    report = evaluate(index, json.loads(Path("evals/rag/queries.json").read_text()))
    assert report["top_5_relevance"] >= report["target"]
    assert report["passed"] is True
