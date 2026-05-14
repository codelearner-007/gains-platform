-- RLS on every per-tenant domain table.
-- dim_standard and dim_strand are GLOBAL lookups (D2 Path A) — no RLS, both
-- schemas are world-readable to authenticated/anon (grants in 045 migration).
--
-- ingestion_runs / user_sync_runs / tenant_config_sync_runs / ingested_files:
-- NO RLS — they are admin telemetry tables accessed only via FastAPI as
-- service_role with RBAC permission checks (e.g. `ingestion:read`). Their
-- school_id column is nullable (NULL = orchestrator-wide / all-tenant run);
-- a per-tenant `school_id = current_setting(...)::uuid` policy would evaluate
-- to NULL on those rows, hiding them from every tenant. Tenant-scoped reads
-- (e.g. "show my school's last sync") happen in FastAPI with explicit
-- WHERE school_id = :school_id filters and RBAC checks. (B1 fix.)
--
-- Pattern per table below:
--   1. ENABLE ROW LEVEL SECURITY
--   2. tenant_iso_select  - tenants see only their school_id rows
--   3. service_role_full  - service_role bypasses for ingestion/transforms

DO $$
DECLARE
  t TEXT;
  tables TEXT[] := ARRAY[
    -- raw layer
    'raw_submission_summary',
    'raw_student_submission',
    'raw_question_data',
    'raw_user',
    -- dimension layer
    'dim_school',
    'dim_student',
    'dim_teacher',
    'dim_parent',
    'dim_course',
    'dim_item',
    'dim_question_data',
    'dim_unit_lesson',
    'dim_section',
    'dim_session',
    'dim_grade',
    'dim_assessment_type',
    'dim_subject',
    -- fact
    'fact_student_submission',
    -- cubes
    'cube_grade_summary',
    'cube_school_summary',
    'cube_standard_summary',
    'cube_question_summary',
    'cube_questionincorrectchoice_summary',
    'cube_question_summary_overall',
    'cube_overallperformance_summary',
    'cube_user_summary',
    -- hash
    'dim_section_hash',
    'dim_student_hash',
    'fact_student_submissions_hash',
    -- tenant config (per-tenant)
    'subject_overrides',
    'subject_course_overrides',
    'teacher_pair_overrides',
    'school_grade_overrides'
    -- ingestion_runs / user_sync_runs / tenant_config_sync_runs /
    -- ingested_files INTENTIONALLY OMITTED — see header comment (B1).
  ];
BEGIN
  FOREACH t IN ARRAY tables LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format(
      'CREATE POLICY tenant_iso_select ON %I FOR SELECT USING (school_id = current_setting(''app.current_school_id'', true)::uuid)',
      t
    );
    EXECUTE format(
      'CREATE POLICY service_role_full ON %I FOR ALL TO service_role USING (true) WITH CHECK (true)',
      t
    );
  END LOOP;
END $$;

-- schools table is the multi-tenant root; tenants only see their own row,
-- service_role manages all schools.
ALTER TABLE schools ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_iso_select ON schools
  FOR SELECT
  USING (school_id = current_setting('app.current_school_id', true)::uuid);
CREATE POLICY service_role_full ON schools
  FOR ALL TO service_role
  USING (true)
  WITH CHECK (true);
