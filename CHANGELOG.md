# Changelog

All notable changes are documented here. The project follows semantic versioning for public SDKs;
the repository remains a pre-1.0 educational prototype.

## [Unreleased]

### Added

- Evidence-indexed portfolio release documentation, safety/limitations material, and a short
  viewer/SDK-first demo runbook.
- Reproducible release audit and source-archive/checksum commands.
- Dataset/model cards, current architecture map, migration guide, release notes, and clean-checkout
  rehearsal record.

### Changed

- The README reviewer path now leads with runnable product surfaces and retained evidence.
- The threat model now covers the browser, ingestion, retrieval, model, MCP, and release boundaries.

### Known gaps

- No approved full C-MAPSS dataset/model artifact is committed, so no production-like RUL metric is
  claimed.
- RAG evidence is a two-query deterministic fixture only; agent quality is not benchmarked.
- API throughput, end-to-end export latency, and whole-system CPU/RSS benchmarks remain unrun.

[Unreleased]: docs/release-notes.md
