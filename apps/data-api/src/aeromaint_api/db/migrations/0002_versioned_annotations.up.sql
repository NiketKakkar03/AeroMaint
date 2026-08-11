ALTER TABLE annotations ADD COLUMN version integer NOT NULL DEFAULT 1 CHECK (version > 0);
ALTER TABLE annotations ADD COLUMN status text NOT NULL DEFAULT 'draft'
  CHECK (status IN ('draft','approved','rejected'));
ALTER TABLE annotations ADD COLUMN actor text NOT NULL DEFAULT 'migration';
ALTER TABLE annotations ADD COLUMN provenance jsonb NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE annotations ADD COLUMN updated_at timestamptz NOT NULL DEFAULT now();
CREATE INDEX annotations_session_time_idx ON annotations(session_id,start_ns,end_ns,id);
