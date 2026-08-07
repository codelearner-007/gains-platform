-- Idempotent recreate of the two DIMENSION hash tables (dim_student_hash,
-- dim_section_hash) so the untouched 08_hash build SQL can run on a box where
-- these were dropped during cleanup (prod dropped all 3 hash tables).
--
-- Scope is deliberately limited to these two dim-hash tables:
--   * fact_student_submissions_hash is NOT recreated here — it stays dropped on
--     prod and its build file is guarded behind to_regclass(...) so the hash
--     derivation is a no-op wherever the fact-hash table is absent.
--   * The twin cube (cube_question_summary_overall_by_item) is untouched here.
--
-- Column list / PRIMARY KEY / UNIQUE / FOREIGN KEY are copied VERBATIM from the
-- original 20260507000080_hash_tables.sql; only IF NOT EXISTS is added so the
-- migration is safe to re-apply and safe on the local box where they already
-- exist.
--
-- RLS RESTORED: CREATE TABLE does not carry over row-level security, so a bare
-- recreate would leave these two tenant tables with RLS DISABLED (open to any
-- role). Each table therefore re-establishes, idempotently, the same three-part
-- policy set every other tenant table carries (ENABLE RLS + tenant_iso_select +
-- service_role_full). The policy bodies are copied VERBATIM from
-- 20260507000090_rls_policies.sql, with the empty-GUC NULLIF guard from
-- 20260601000050_rls_failclosed_empty_guc.sql, so a box recreating these tables
-- lands in exactly the state the two RLS migrations left them in. DROP POLICY IF
-- EXISTS + CREATE makes each policy safe to re-apply on the local box (and the
-- clone) where they already exist.

CREATE TABLE IF NOT EXISTS dim_section_hash (
  section_nid          TEXT NOT NULL,
  school_id            UUID NOT NULL REFERENCES schools(school_id) ON DELETE CASCADE,
  section_instructors  TEXT,
  teacher_name_hash    TEXT,
  PRIMARY KEY (school_id, section_nid),
  UNIQUE (school_id, teacher_name_hash)
);
CREATE INDEX IF NOT EXISTS dim_section_hash_school_idx ON dim_section_hash (school_id);
CREATE INDEX IF NOT EXISTS dim_section_hash_teacher_idx ON dim_section_hash (school_id, teacher_name_hash);

ALTER TABLE dim_section_hash ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_iso_select ON dim_section_hash;
CREATE POLICY tenant_iso_select ON dim_section_hash FOR SELECT
  USING (school_id = NULLIF(current_setting('app.current_school_id', true), '')::uuid);
DROP POLICY IF EXISTS service_role_full ON dim_section_hash;
CREATE POLICY service_role_full ON dim_section_hash FOR ALL TO service_role
  USING (true) WITH CHECK (true);

CREATE TABLE IF NOT EXISTS dim_student_hash (
  user_uid           TEXT NOT NULL,
  school_id          UUID NOT NULL REFERENCES schools(school_id) ON DELETE CASCADE,
  user_name          TEXT,
  student_name_hash  TEXT,
  PRIMARY KEY (school_id, user_uid),
  UNIQUE (school_id, student_name_hash)
);
CREATE INDEX IF NOT EXISTS dim_student_hash_school_idx ON dim_student_hash (school_id);
CREATE INDEX IF NOT EXISTS dim_student_hash_student_idx ON dim_student_hash (school_id, student_name_hash);

ALTER TABLE dim_student_hash ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_iso_select ON dim_student_hash;
CREATE POLICY tenant_iso_select ON dim_student_hash FOR SELECT
  USING (school_id = NULLIF(current_setting('app.current_school_id', true), '')::uuid);
DROP POLICY IF EXISTS service_role_full ON dim_student_hash;
CREATE POLICY service_role_full ON dim_student_hash FOR ALL TO service_role
  USING (true) WITH CHECK (true);
