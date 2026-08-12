# Hybrid retrieval evaluation

The curated fixture contains five cases: two exact-terminology queries, two semantic paraphrases, and
one unsupported-query abstention. The deterministic local profile reaches **100% top-5 relevance
(5/5)** against the approved NASA/FAA excerpt fixture, exceeding the documented 80% release target.

This report is a reproducible contract result. Before a release, run `evals/rag/evaluate.py` against
the checksum-pinned full corpus and retain its JSON output. Any score below 80%, any failed exact-term
case, or any failed abstention is a reported release gap rather than silently relaxing the threshold.
