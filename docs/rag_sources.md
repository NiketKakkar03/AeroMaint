# Retrieval sources and safety boundary

AeroMaint indexes only explicitly approved, locally supplied documents. Each source manifest records
an HTTPS canonical URL, title, edition/version, optional page, local path, and `approved: true`.
Ingestion refuses unapproved entries and paths outside the manifest directory. Rebuilding the same
corpus produces the same index version and does not rewrite an identical index.

The built-in API fixture contains short descriptive excerpts linked to NASA NTRS and FAA AC 43.13-1B.
It exists for deterministic contract tests and is not a substitute for the complete publications.
Full documents are deliberately not redistributed here; an operator must review licensing, download
from the canonical publisher, verify checksums, and approve the manifest.

Search combines exact token frequency with a deterministic local feature-hash embedding via reciprocal
rank fusion. Every result retains URL, title, version, page, section, and stable chunk ID. Queries with
no positive lexical or semantic evidence return `insufficient_evidence`. This retrieval output is
evidence for review, never authority for an airworthiness or return-to-service decision.
