-- Ingestion durability (HARDENING_PLAN §2).
--
-- ADDITIVE + IDEMPOTENT + PROD-SAFE. Every statement is IF NOT EXISTS /
-- ADD COLUMN IF NOT EXISTS / ON CONFLICT DO NOTHING, and every CHECK is added
-- NOT VALID so existing rows are never re-validated (a full-table scan that
-- could fail on prod's current state is avoided). Nothing here reads or mutates
-- data: the durable worker/queue columns, the warehouse_state singleton, and
-- the schools pointer/guards are all inert until the backend that uses them is
-- deployed. On prod (raw=0, transforms disabled) these stay dormant.

-- 1. Durable-queue columns on ingestion_runs.
--    claimed_at / heartbeat_at / worker_id back the lease-based claim + reaper;
--    attempt_count caps requeues; transforms_applied records whether the run's
--    landing was followed by a transform pass. All nullable/defaulted so the
--    ADD is instant and existing rows are valid.
ALTER TABLE ingestion_runs
  ADD COLUMN IF NOT EXISTS claimed_at        TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS heartbeat_at      TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS worker_id         TEXT,
  ADD COLUMN IF NOT EXISTS attempt_count     INTEGER NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS transforms_applied BOOLEAN;

-- Status vocabulary for the durable state machine:
--   pending -> running -> landed -> transforming -> succeeded | failed
-- Added NOT VALID: legacy rows (status 'running'/'succeeded'/'failed') are all
-- inside the set, but NOT VALID skips the scan and keeps the migration instant
-- and safe regardless of any historical value.
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'ingestion_runs_status_check'
  ) THEN
    ALTER TABLE ingestion_runs
      ADD CONSTRAINT ingestion_runs_status_check
      CHECK (status IN ('pending','running','landed','transforming','succeeded','failed'))
      NOT VALID;
  END IF;
END $$;

-- 2. warehouse_state — single-row (id=1) dirty flag for the transform gate.
--    Set dirty (with a token = the run_id that marked it) BEFORE landing raw;
--    cleared atomically in the same txn that rebuilds cubes. A crash mid-
--    transform rolls back both the cubes and the clear, so the reaper re-runs.
CREATE TABLE IF NOT EXISTS warehouse_state (
  id                   SMALLINT PRIMARY KEY DEFAULT 1,
  transforms_dirty     BOOLEAN NOT NULL DEFAULT false,
  dirty_since          TIMESTAMPTZ,
  dirty_token          UUID,
  last_transform_run_id UUID,
  last_transform_at    TIMESTAMPTZ,
  CHECK (id = 1)
);
INSERT INTO warehouse_state (id, transforms_dirty) VALUES (1, false)
  ON CONFLICT (id) DO NOTHING;

-- 3. schools.credential_ref — non-secret pointer into the scraper's
--    SCHOOLOGY_CREDENTIALS env map (contract v1.1, additive). Nullable; the
--    scraper falls back to short_name / default / legacy flat env. NO secret is
--    ever stored here.
ALTER TABLE schools
  ADD COLUMN IF NOT EXISTS credential_ref TEXT;

-- 4. schools.short_name integrity (F22).
--    Unique so a school can be resolved by short_name for storage keys/archive;
--    and the archive namespace 'processed/' is reserved, so no school may claim
--    short_name = 'processed'. The CHECK is NOT VALID (no existing 'processed'
--    school on any env; the scan is skipped for prod safety).
CREATE UNIQUE INDEX IF NOT EXISTS schools_short_name_uq ON schools (short_name);
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'schools_short_name_not_processed'
  ) THEN
    ALTER TABLE schools
      ADD CONSTRAINT schools_short_name_not_processed
      CHECK (short_name <> 'processed')
      NOT VALID;
  END IF;
END $$;

-- 5. Partial index over the active run states so the claim/reaper scans stay
--    cheap regardless of how many terminal (succeeded/failed) rows accumulate.
CREATE INDEX IF NOT EXISTS ingestion_runs_active_idx
  ON ingestion_runs (status)
  WHERE status IN ('pending','running','landed','transforming');
