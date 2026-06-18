-- RLS policies for cube_question_summary_overall_by_item (the per-item twin
-- of cube_question_summary_overall). FIX for the Standards Deep Dive showing
-- "0.0%" strand tiles + blank "Correct % by Standard" bars in production.
--
-- ROOT CAUSE: migration 20260616000000 created this table but added NO RLS
-- policy. Supabase auto-enables ROW LEVEL SECURITY on new public-schema
-- tables, so the twin ended up RLS-ENABLED with ZERO POLICIES = deny-all to
-- every non-bypass role. The service_role (and direct/MCP superuser) BYPASSES
-- RLS, so the data looked perfect in every direct-DB check and the rebuild
-- populated 72k rows fine. But the FastAPI backend runs under the tenant role
-- and sets `app.current_school_id` per request; with no SELECT policy it read
-- ZERO rows from the twin -> get_strand_rollup_for_item /
-- get_standard_rollup_for_item returned NULL grade_average -> the SDD strand
-- treemap rendered 0.0% and the per-standard bars were blank. The
-- cube_question_summary-sourced bands + KPIs (which carry the policy) rendered
-- correctly, which is why only the twin-sourced fields were affected.
--
-- FIX: replicate the EXACT two policies every other cube table carries
-- (cf. cube_question_summary_overall): full access for service_role +
-- tenant-isolated SELECT keyed on app.current_school_id. This preserves
-- multi-tenant isolation (a user only sees their school's rows). Idempotent.

ALTER TABLE public.cube_question_summary_overall_by_item ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS service_role_full ON public.cube_question_summary_overall_by_item;
CREATE POLICY service_role_full ON public.cube_question_summary_overall_by_item
  FOR ALL TO service_role USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS tenant_iso_select ON public.cube_question_summary_overall_by_item;
CREATE POLICY tenant_iso_select ON public.cube_question_summary_overall_by_item
  FOR SELECT TO public
  USING (school_id = (NULLIF(current_setting('app.current_school_id'::text, true), ''::text))::uuid);
