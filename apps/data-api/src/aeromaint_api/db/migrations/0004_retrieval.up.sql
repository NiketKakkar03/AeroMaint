CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE retrieval_indexes (
  version text PRIMARY KEY,
  active boolean NOT NULL DEFAULT false,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX retrieval_one_active_idx ON retrieval_indexes(active) WHERE active;

CREATE TABLE retrieval_chunks (
  chunk_id text NOT NULL,
  index_version text NOT NULL REFERENCES retrieval_indexes(version) ON DELETE CASCADE,
  source_url text NOT NULL,
  title text NOT NULL,
  document_version text NOT NULL,
  page integer,
  section text NOT NULL,
  start_char integer NOT NULL,
  end_char integer NOT NULL,
  checksum char(64) NOT NULL,
  content text NOT NULL,
  search_vector tsvector GENERATED ALWAYS AS
    (to_tsvector('english', section || ' ' || content)) STORED,
  embedding vector(96) NOT NULL,
  PRIMARY KEY (index_version, chunk_id),
  CHECK (start_char >= 0 AND end_char > start_char),
  CHECK (source_url LIKE 'https://%')
);
CREATE INDEX retrieval_chunks_fts_idx ON retrieval_chunks USING gin(search_vector);
CREATE INDEX retrieval_chunks_vector_idx ON retrieval_chunks USING hnsw (embedding vector_cosine_ops);
