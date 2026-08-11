# Hybrid retrieval evaluation

The deterministic two-query smoke corpus reaches **100% top-5 title relevance (2/2)**. This is a
contract fixture, not a claim about broad NASA/FAA retrieval quality. A release evaluation must use
the approved, checksum-pinned source corpus documented in `docs/rag_sources.md`.

The gate is: all curated exact-terminology queries and at least 80% of semantic paraphrases return a
relevant source in the top five; unsupported queries must return `insufficient_evidence`.
