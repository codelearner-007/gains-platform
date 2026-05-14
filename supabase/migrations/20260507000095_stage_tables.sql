-- Phase 2 staging tables.
-- These hold the type-coerced + tenant-override-resolved versions of the
-- corresponding raw_* tables. Downstream dim builds query stg_* (not raw_*)
-- to keep override logic out of every dim and in one place.
--
-- NOT per-tenant — staging is rebuilt by the transformation orchestrator on
-- every run. Tenancy is enforced by the school_id column resolved from
-- raw.user_school_id (CSV) -> schools.schoology_school_id (UUID), and any
-- downstream model JOINing in must filter by school_id when needed.
--
-- Each stg_* runs as TRUNCATE + INSERT (Postgres equivalent of overwrite mode);
-- there is no ON CONFLICT path here because the raw_* tables are the
-- system-of-record for re-runs. Idempotency is `truncate + insert from raw`
-- and the input raw_* tables already enforce uniqueness on (school_id,
-- source_file_hash, unique_key).

CREATE TABLE IF NOT EXISTS stg_student_submission (
  school_id              UUID NOT NULL REFERENCES schools(school_id) ON DELETE CASCADE,
  user_uid               TEXT,
  username               TEXT,
  last_name              TEXT,
  first_name             TEXT,
  user_role_id           TEXT,
  user_school_id         TEXT,
  user_school_name       TEXT,
  course_nid             TEXT,
  course_name            TEXT,
  course_code            TEXT,
  section_nid            TEXT,
  section_name           TEXT,
  section_code           TEXT,
  section_instructors    TEXT,
  item_type              TEXT,
  item_id                TEXT,
  item_name              TEXT,
  first_access           TIMESTAMPTZ,
  latest_attempt         TIMESTAMPTZ,
  total_time             INTERVAL,
  submission_grade       NUMERIC(10,4),
  submission             INTEGER,
  question_id            TEXT,
  associated_question_id TEXT,
  question_type          TEXT,
  question               TEXT,
  position_number        TEXT,
  sub_question           TEXT,
  answer_submission      TEXT,
  correct_answer         TEXT,
  points_received        NUMERIC(10,4),
  points_possible        NUMERIC(10,4),
  session                TEXT,
  assessment_type        TEXT,
  subject                TEXT,
  grade                  TEXT,
  section                TEXT,
  file_name              TEXT
);
CREATE INDEX IF NOT EXISTS stg_student_submission_school_idx
  ON stg_student_submission (school_id);
CREATE INDEX IF NOT EXISTS stg_student_submission_school_item_idx
  ON stg_student_submission (school_id, item_id);
CREATE INDEX IF NOT EXISTS stg_student_submission_school_role_idx
  ON stg_student_submission (school_id, user_role_id);

CREATE TABLE IF NOT EXISTS stg_question_data (
  school_id               UUID NOT NULL REFERENCES schools(school_id) ON DELETE CASCADE,
  item_id                 TEXT,
  item_name               TEXT,
  question_id             TEXT,
  associated_question_id  TEXT,
  total_points            NUMERIC(10,4),
  question_type           TEXT,
  question                TEXT,
  position_number         TEXT,
  sub_question            TEXT,
  answer_option           TEXT,
  answer_breakdown_count  INTEGER,
  answer_breakdown_pct    NUMERIC(10,4),
  correct_answer          TEXT,
  correctly_answered      NUMERIC(10,4),
  most_points_earned      NUMERIC(10,4),
  least_points_earned     NUMERIC(10,4),
  average_points_earned   NUMERIC(10,4),
  standards_val           TEXT,
  session                 TEXT,
  assessment_type         TEXT,
  subject                 TEXT,
  grade                   TEXT,
  section                 TEXT,
  file_name               TEXT,
  question_no             TEXT
);
CREATE INDEX IF NOT EXISTS stg_question_data_school_idx
  ON stg_question_data (school_id);
CREATE INDEX IF NOT EXISTS stg_question_data_school_item_idx
  ON stg_question_data (school_id, item_id);
CREATE INDEX IF NOT EXISTS stg_question_data_standards_idx
  ON stg_question_data (standards_val);

CREATE TABLE IF NOT EXISTS stg_submission_summary (
  school_id          UUID NOT NULL REFERENCES schools(school_id) ON DELETE CASCADE,
  schoology_id       TEXT,
  first_name         TEXT,
  last_name          TEXT,
  unique_id_csv      TEXT,
  job_title          TEXT,
  gradebook_grade    TEXT,
  submission_no      INTEGER,
  submission_score   NUMERIC(10,4),
  question_label     TEXT,
  question_score     NUMERIC(10,4)
);
CREATE INDEX IF NOT EXISTS stg_submission_summary_school_idx
  ON stg_submission_summary (school_id);

-- stg_user mirrors raw_user 1:1 (no overrides apply here). The dim builds for
-- student/teacher/parent fall back to stg_student_submission if stg_user is
-- empty (Phase 7 introduces sync_users.py to populate raw_user).
CREATE TABLE IF NOT EXISTS stg_user (
  school_id                UUID NOT NULL REFERENCES schools(school_id) ON DELETE CASCADE,
  uid                      TEXT,
  id                       TEXT,
  school_uid               TEXT,
  name_title               TEXT,
  name_first               TEXT,
  name_first_preferred     TEXT,
  use_preferred_first_name BOOLEAN,
  name_middle              TEXT,
  name_middle_show         BOOLEAN,
  name_last                TEXT,
  name_display             TEXT,
  primary_email            TEXT,
  picture_url              TEXT,
  gender                   TEXT,
  position                 TEXT,
  grad_year                TEXT,
  username                 TEXT,
  password_hash            TEXT,
  role_id                  TEXT,
  tz_offset                TEXT,
  tz_name                  TEXT,
  language                 TEXT,
  child_uids               TEXT[],
  user_school_id           TEXT,
  is_active                BOOLEAN
);
CREATE INDEX IF NOT EXISTS stg_user_school_idx ON stg_user (school_id);
CREATE INDEX IF NOT EXISTS stg_user_school_role_idx ON stg_user (school_id, role_id);
