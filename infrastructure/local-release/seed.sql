CREATE TABLE IF NOT EXISTS local_demo_sessions (
  id text PRIMARY KEY,
  title text NOT NULL,
  fixture_path text NOT NULL,
  seeded_at timestamptz NOT NULL DEFAULT now()
);
INSERT INTO local_demo_sessions (id, title, fixture_path)
VALUES ('synthetic-session', 'Synthetic inspection flight', 'tests/media-fixtures/synthetic-session')
ON CONFLICT (id) DO UPDATE SET title = EXCLUDED.title, fixture_path = EXCLUDED.fixture_path;
