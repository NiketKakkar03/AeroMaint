# Retrieval sources, licensing, and evaluation

AeroMaint only indexes operator-supplied documents explicitly approved in a versioned JSON manifest.
The repository does not redistribute NASA or FAA publications. This preserves publisher terms and
keeps the runtime local and zero-cost. An approver must confirm the document's reuse terms; metadata
is an audit record, not legal advice.

Each source entry requires `approved: true`, `approved_by`, `license`, canonical HTTPS `url`, `title`,
publication `version`, relative `path`, and lowercase `sha256`. A minimal entry is:

```json
{
  "approved": true,
  "approved_by": "engineering-library-review",
  "license": "reviewed publisher terms",
  "url": "https://ntrs.nasa.gov/citations/20090029214",
  "title": "NASA C-MAPSS turbofan degradation simulation",
  "version": "2008",
  "path": "artifacts/nasa-cmapss.pdf",
  "sha256": "<64 lowercase hexadecimal characters>"
}
```

`make rag-acquire RAG_MANIFEST=...` downloads only missing files, verifies bytes before an atomic
rename, and re-verifies existing files. `make rag-index` parses text or PDF pages, rejects malformed,
encrypted, empty, NUL-containing, missing, and checksum-mismatched inputs, then publishes an index
atomically. Identical input produces the same index version and leaves the existing file untouched.

Every chunk records source URL/title/version/checksum, one-based PDF page (or a manifest override),
section, and exact `start_char`/`end_char` offsets. Search returns those fields with the matching text,
so callers can verify the span. Unsupported input returns `insufficient_evidence`; retrieved passages
remain review evidence, never authority for airworthiness or return-to-service decisions.

The default local profile uses deterministic 96-dimensional word/character feature hashing and no
paid service or model download. The PostgreSQL profile migration enables pgvector, a generated English
`tsvector` with GIN, a cosine HNSW index, and reciprocal-rank fusion. Reindexing inserts an immutable
corpus version once and changes the active version transactionally.

## Evaluation gate

Run `make rag-evaluate RAG_INDEX=...`. The checked-in curated set covers exact NASA/FAA terminology,
semantic paraphrases, and abstention. The release target is at least **80% top-5 relevance**, with all
exact terminology cases and unsupported-query abstention passing. The deterministic five-query fixture
currently reaches **100% (5/5)**; this is a contract result, not a claim about an unreviewed full corpus.
