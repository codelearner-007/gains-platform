CREATE TABLE ingestion_runs (
  run_id          UUID PRIMARY KEY DEFAULT uuid_generate_v7(),
  school_id       UUID REFERENCES schools(school_id),
  started_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  finished_at     TIMESTAMPTZ,
  status          TEXT NOT NULL DEFAULT 'running',
  files_processed INTEGER NOT NULL DEFAULT 0,
  rows_inserted   INTEGER NOT NULL DEFAULT 0,
  error_count     INTEGER NOT NULL DEFAULT 0,
  error_details   JSONB
);
CREATE INDEX ingestion_runs_school_started_idx ON ingestion_runs (school_id, started_at DESC);
CREATE INDEX ingestion_runs_status_idx ON ingestion_runs (status);

CREATE TABLE ingested_files (
  file_id           UUID PRIMARY KEY DEFAULT uuid_generate_v7(),
  school_id         UUID NOT NULL REFERENCES schools(school_id) ON DELETE CASCADE,
  blob_path         TEXT NOT NULL,
  file_hash         TEXT NOT NULL,
  file_type         TEXT NOT NULL,
  ingested_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  rows_ingested     INTEGER NOT NULL,
  ingestion_run_id  UUID NOT NULL REFERENCES ingestion_runs(run_id),
  UNIQUE (school_id, file_hash)
);
CREATE INDEX ingested_files_school_idx ON ingested_files (school_id);
CREATE INDEX ingested_files_run_idx ON ingested_files (ingestion_run_id);

-- D2 Path A (user decision 2026-05-06): no standards_sync_runs table.
-- dim_standard / dim_strand are static seeds loaded once; no live sync.

CREATE TABLE user_sync_runs (
  run_id        UUID PRIMARY KEY DEFAULT uuid_generate_v7(),
  school_id     UUID REFERENCES schools(school_id),
  started_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  finished_at   TIMESTAMPTZ,
  status        TEXT NOT NULL DEFAULT 'running',
  rows_upserted INTEGER NOT NULL DEFAULT 0,
  error_details JSONB
);
CREATE INDEX user_sync_runs_school_started_idx ON user_sync_runs (school_id, started_at DESC);

CREATE TABLE tenant_config_sync_runs (
  run_id        UUID PRIMARY KEY DEFAULT uuid_generate_v7(),
  school_id     UUID REFERENCES schools(school_id),
  started_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  finished_at   TIMESTAMPTZ,
  status        TEXT NOT NULL DEFAULT 'running',
  rows_upserted INTEGER NOT NULL DEFAULT 0,
  error_details JSONB
);
CREATE INDEX tenant_config_sync_runs_school_started_idx ON tenant_config_sync_runs (school_id, started_at DESC);
