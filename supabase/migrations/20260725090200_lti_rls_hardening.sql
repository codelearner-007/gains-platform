-- ============================================================================
-- LTI infra tables — RLS hardening (defense-in-depth)
-- ============================================================================
-- REVISES the stance documented in 20260601000020_lti.sql:64-65 and
-- 20260724090000_lti_handoff_ticket.sql. Those migrations left the five lti_*
-- tables with RLS OFF and relied SOLELY on the connection role: the LTI /
-- machine-auth path uses plain get_db (no role switch), so it stays on the
-- RLS-BYPASSING backend role (locally `postgres`, in prod `service_role` —
-- both have rolbypassrls). That is correct, but it is a single line of defense.
--
-- The gap it leaves: `anon` and `authenticated` currently hold blanket table
-- grants on every lti_* table (Supabase's default GRANT ALL … TO anon,
-- authenticated). With RLS off, ANY code path that runs under the tenant
-- `authenticated` role — e.g. the RLS middleware's `SET LOCAL ROLE
-- authenticated` — could SELECT `tool_private_key`, handoff `ticket`s, `sub`
-- identities, and launch nonces. Nothing does today, but that is exactly the
-- kind of latent read this project treats as a bug (CLAUDE.md common mistake
-- #14: never leave GRANT ALL to anon/authenticated as the only guard).
--
-- This migration turns the stance from "RLS off, rely on the role" into
-- "RLS deny-all to the tenant role; the service/bypass role still bypasses":
--
--   * ENABLE (not FORCE) ROW LEVEL SECURITY on all five lti_* tables.
--   * Create NO permissive policy. With RLS enabled and zero policies, every
--     non-bypass role (`authenticated`, `anon`) is DENIED all rows — the tenant
--     role can no longer read tool_private_key or tickets.
--   * The backend keeps working untouched: `postgres` (local) and `service_role`
--     (prod) both have BYPASSRLS, so they bypass the (empty) policy set entirely.
--     No `service_role_full` policy is added on purpose — it would be INERT
--     (BYPASSRLS never consults policies), i.e. cargo-cult; the per-tenant tables
--     carry one only because that migration created it uniformly in a loop.
--
-- Why ENABLE, not FORCE: FORCE would also subject a table *owner* to RLS, which
-- risks locking out an owner/maintenance role for no security gain — a superuser
-- / BYPASSRLS role bypasses FORCE anyway, so FORCE would be inert against the
-- roles that matter here while adding owner-lockout risk. ENABLE matches the
-- existing tenant-table pattern (20260507000090_rls_policies.sql).
--
-- Idempotent: ENABLE ROW LEVEL SECURITY is a no-op when already enabled.
-- ============================================================================

ALTER TABLE public.lti_registration    ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.lti_deployment       ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.lti_launch_session   ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.lti_user_identity    ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.lti_handoff_ticket   ENABLE ROW LEVEL SECURITY;

COMMENT ON TABLE public.lti_registration IS
  'LTI trust config. RLS ENABLED with NO policy → deny-all to authenticated/anon (protects tool_private_key); the RLS-bypassing backend role (postgres/service_role) still bypasses. See 20260725090200_lti_rls_hardening.sql.';
COMMENT ON TABLE public.lti_handoff_ticket IS
  'FastAPI/service_role-managed single-use LTI session handoff tickets. RLS ENABLED with NO policy → deny-all to authenticated/anon; the RLS-bypassing backend role bypasses (machine-auth path, no user JWT). See 20260725090200_lti_rls_hardening.sql.';
