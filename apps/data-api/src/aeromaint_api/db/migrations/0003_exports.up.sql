CREATE TABLE exports (
  id uuid PRIMARY KEY,
  idempotency_key text NOT NULL,
  session_id text NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
  actor text NOT NULL,
  start_ns bigint NOT NULL,
  end_ns bigint NOT NULL,
  stream_ids jsonb NOT NULL,
  sensor_format text NOT NULL DEFAULT 'arrow',
  include_annotations boolean NOT NULL DEFAULT true,
  status text NOT NULL DEFAULT 'pending',
  progress double precision NOT NULL DEFAULT 0,
  cancel_requested boolean NOT NULL DEFAULT false,
  manifest jsonb,
  error jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  expires_at timestamptz NOT NULL,
  UNIQUE (actor, idempotency_key),
  CHECK (end_ns > start_ns),
  CHECK (sensor_format IN ('arrow','json')),
  CHECK (status IN ('pending','running','succeeded','failed','cancelled','expired')),
  CHECK (progress >= 0 AND progress <= 1)
);
CREATE INDEX exports_session_actor_idx ON exports(session_id, actor, created_at);
CREATE INDEX exports_claim_idx ON exports(status, created_at) WHERE status = 'pending';
