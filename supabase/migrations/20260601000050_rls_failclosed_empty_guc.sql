-- Fail-closed hardening for the no-membership tenant case.
--
-- The per-tenant SELECT policies created in 20260507000090_rls_policies.sql use:
--     USING (school_id = current_setting('app.current_school_id', true)::uuid)
--
-- When a request never sets the GUC (a member with NO school membership — the
-- intended fail-closed path), `current_setting('app.current_school_id', true)`
-- returns the EMPTY STRING, and `''::uuid` raises
-- `invalid input syntax for type uuid: ""`. The middleware already switches to
-- the `authenticated` role and leaves the GUC unset on purpose so RLS returns
-- zero rows — but the bare cast turns that zero-row outcome into a 500 instead.
--
-- This migration recreates every tenant_iso_select policy with a NULLIF guard:
--     NULLIF(current_setting('app.current_school_id', true), '')::uuid
-- An unset GUC now yields NULL, so `school_id = NULL` is NULL (never true) and
-- the policy matches zero rows cleanly. The security property is unchanged
-- (still fail-closed, no cross-tenant data); only the error path is fixed.
--
-- Idempotent: drops + recreates the named policy on each listed table.

DO $$
DECLARE
  t TEXT;
  tables TEXT[] := ARRAY[
    'raw_submission_summary',
    'raw_student_submission',
    'raw_question_data',
    'raw_user',
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
    'fact_student_submission',
    'cube_grade_summary',
    'cube_school_summary',
    'cube_standard_summary',
    'cube_question_summary',
    'cube_questionincorrectchoice_summary',
    'cube_question_summary_overall',
    'cube_overallperformance_summary',
    'cube_user_summary',
    'dim_section_hash',
    'dim_student_hash',
    'fact_student_submissions_hash',
    'subject_overrides',
    'subject_course_overrides',
    'teacher_pair_overrides',
    'school_grade_overrides'
  ];
BEGIN
  FOREACH t IN ARRAY tables LOOP
    EXECUTE format('DROP POLICY IF EXISTS tenant_iso_select ON %I', t);
    EXECUTE format(
      'CREATE POLICY tenant_iso_select ON %I FOR SELECT '
      'USING (school_id = NULLIF(current_setting(''app.current_school_id'', true), '''')::uuid)',
      t
    );
  END LOOP;
END $$;

-- schools (multi-tenant root) — same guard.
DROP POLICY IF EXISTS tenant_iso_select ON schools;
CREATE POLICY tenant_iso_select ON schools
  FOR SELECT
  USING (school_id = NULLIF(current_setting('app.current_school_id', true), '')::uuid);
