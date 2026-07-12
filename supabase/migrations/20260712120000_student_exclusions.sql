-- =============================================================================
-- student_exclusions — durable per-(school, user_uid) student-account exclusions
-- applied at staging (stg_student_submission) so the account and all its rows
-- never enter staging/dims/facts/cubes.
--
-- WHY: some Schoology instances contain internal STAFF/DEMO/SANDBOX test accounts
-- (adults clicking through assessments to try the platform). They inflate
-- distinct-headcount KPIs and render phantom sandbox report cards. Confirmed
-- internal accounts should be dropped at ingest, not shown as students.
--
-- Grain: (school_id, user_uid). Reason documents the confirmation.
-- =============================================================================

CREATE TABLE IF NOT EXISTS student_exclusions (
  school_id  UUID NOT NULL REFERENCES schools(school_id) ON DELETE CASCADE,
  user_uid   TEXT NOT NULL,
  reason     TEXT,
  source     TEXT NOT NULL DEFAULT 'audit-2026-07',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (school_id, user_uid)
);

CREATE INDEX IF NOT EXISTS student_exclusions_school_idx
  ON student_exclusions (school_id);
