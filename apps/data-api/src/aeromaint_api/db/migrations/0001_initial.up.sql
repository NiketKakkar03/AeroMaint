CREATE TABLE sessions (
  id text PRIMARY KEY, display_name text NOT NULL, start_ns bigint NOT NULL, end_ns bigint NOT NULL,
  manifest jsonb NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT sessions_range CHECK (end_ns >= start_ns)
);
CREATE TABLE artifacts (
  id text NOT NULL, session_id text NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
  media_type text NOT NULL, logical_key text NOT NULL, size_bytes bigint NOT NULL CHECK (size_bytes >= 0),
  sha256 char(64) NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (session_id, id), UNIQUE (session_id, logical_key),
  CHECK (sha256 ~ '^[a-f0-9]{64}$')
);
CREATE TABLE streams (
  id text NOT NULL, session_id text NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
  kind text NOT NULL, clock_id text NOT NULL, start_ns bigint NOT NULL, end_ns bigint NOT NULL,
  sample_count bigint NOT NULL CHECK (sample_count >= 0), schema_ref text NOT NULL,
  PRIMARY KEY (session_id, id), CHECK (end_ns >= start_ns)
);
CREATE TABLE stream_artifacts (
  session_id text NOT NULL, stream_id text NOT NULL, artifact_id text NOT NULL,
  PRIMARY KEY (session_id, stream_id, artifact_id),
  FOREIGN KEY (session_id, stream_id) REFERENCES streams(session_id, id) ON DELETE CASCADE,
  FOREIGN KEY (session_id, artifact_id) REFERENCES artifacts(session_id, id) ON DELETE CASCADE
);
CREATE TABLE gaps (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY, session_id text NOT NULL, stream_id text NOT NULL,
  start_ns bigint NOT NULL, end_ns bigint NOT NULL, reason text NOT NULL,
  FOREIGN KEY (session_id, stream_id) REFERENCES streams(session_id, id) ON DELETE CASCADE,
  CHECK (end_ns >= start_ns), CHECK (reason IN ('missing','corrupt','clock_discontinuity'))
);
CREATE TABLE imports (
  id uuid PRIMARY KEY, idempotency_key text NOT NULL UNIQUE, source_uri text NOT NULL,
  status text NOT NULL DEFAULT 'pending', session_id text REFERENCES sessions(id),
  error jsonb, created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
  CHECK (status IN ('pending','running','succeeded','failed'))
);
CREATE TABLE annotations (
  id uuid PRIMARY KEY, session_id text NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
  stream_id text, start_ns bigint NOT NULL, end_ns bigint NOT NULL, kind text NOT NULL,
  payload jsonb NOT NULL DEFAULT '{}'::jsonb, created_at timestamptz NOT NULL DEFAULT now(),
  CHECK (end_ns >= start_ns),
  FOREIGN KEY (session_id, stream_id) REFERENCES streams(session_id, id)
);
CREATE TABLE audit_events (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY, occurred_at timestamptz NOT NULL DEFAULT now(),
  actor text NOT NULL, action text NOT NULL, entity_type text NOT NULL, entity_id text NOT NULL,
  payload jsonb NOT NULL DEFAULT '{}'::jsonb
);
CREATE FUNCTION reject_audit_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'audit_events are append-only' USING ERRCODE = '55000'; END $$;
CREATE TRIGGER audit_events_append_only BEFORE UPDATE OR DELETE ON audit_events
FOR EACH ROW EXECUTE FUNCTION reject_audit_mutation();
CREATE INDEX artifacts_session_idx ON artifacts(session_id);
CREATE INDEX streams_session_idx ON streams(session_id);
CREATE INDEX audit_entity_idx ON audit_events(entity_type, entity_id, occurred_at);
