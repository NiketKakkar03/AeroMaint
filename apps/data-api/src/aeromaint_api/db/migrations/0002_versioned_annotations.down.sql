DROP INDEX IF EXISTS annotations_session_time_idx;
ALTER TABLE annotations DROP COLUMN updated_at;
ALTER TABLE annotations DROP COLUMN provenance;
ALTER TABLE annotations DROP COLUMN actor;
ALTER TABLE annotations DROP COLUMN status;
ALTER TABLE annotations DROP COLUMN version;
