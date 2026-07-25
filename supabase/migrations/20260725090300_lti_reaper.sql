-- ============================================================================
-- LTI ephemeral-table reaper (pg_cron) — bounds unbounded growth
-- ============================================================================
-- Two LTI infra tables accumulate one row per event and never self-delete:
--   * lti_launch_session  — one row per OIDC login-init (~5 min TTL). _consume_state
--     marks/consumes the matching row on launch but leaves it (and every
--     abandoned login-init that never launched) in place.
--   * lti_handoff_ticket  — one row per successful launch (~60 s TTL). Consumed
--     tickets flip `consumed = TRUE` but are never removed.
-- Both carry `expires_at`; once past it a row is dead weight. Without a sweep the
-- tables grow forever once LTI is enabled. This migration adds a periodic reaper.
--
-- ── The RLS subtlety (why SECURITY DEFINER) ────────────────────────────────
-- 20260725090200_lti_rls_hardening.sql ENABLEd RLS with NO policy on both tables
-- → deny-all to `authenticated`/`anon`; only BYPASSRLS roles (postgres locally,
-- service_role in prod) can touch rows. A cron job's SQL runs as the job's owning
-- role, which is NOT guaranteed to bypass RLS. So the reaper is a SECURITY
-- DEFINER procedure OWNED BY the migration runner (postgres / supabase_admin —
-- BYPASSRLS): it executes with the definer's privileges and bypasses the Wave-5
-- deny-all WITHOUT weakening it. This mirrors the repo's existing privileged-DB
-- pattern (public.enforce_single_super_admin, 20260717120000, is likewise a
-- SECURITY DEFINER plpgsql routine in `public`). No RLS policy is relaxed.
--
-- ── Expired-only is sufficient ─────────────────────────────────────────────
-- Deleting `expires_at < now()` bounds growth: every row is TTL-bounded, so it
-- becomes reap-eligible within minutes of creation regardless of consumed state.
-- Consumed-but-unexpired rows linger at most one TTL — negligible. Both tables
-- have an `expires_at` btree index, so the sweep is a cheap ranged delete.
--
-- Cadence: every 10 minutes — comfortably inside the ~5 min launch-session TTL,
-- so the steady-state backlog stays tiny.
--
-- Idempotent: CREATE OR REPLACE for the procedure; unschedule-then-schedule for
-- the cron job. Touches ONLY the two lti_* tables. pg_cron is a managed Supabase
-- extension in prod; guarded for local dev where it may be absent.
-- ============================================================================

-- Reaper procedure — SECURITY DEFINER (owner bypasses the Wave-5 deny-all RLS).
CREATE OR REPLACE FUNCTION public.reap_lti_ephemeral()
RETURNS void AS $$
BEGIN
    DELETE FROM public.lti_launch_session WHERE expires_at < now();
    DELETE FROM public.lti_handoff_ticket WHERE expires_at < now();
END;
$$ LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp;

COMMENT ON FUNCTION public.reap_lti_ephemeral() IS
  'Deletes expired lti_launch_session + lti_handoff_ticket rows. SECURITY DEFINER so the owning (BYPASSRLS) role bypasses the Wave-5 deny-all RLS without weakening it. Scheduled every 10 min via pg_cron; also invokable manually.';

-- Schedule the sweep via pg_cron (managed in prod). Guarded so a dev DB without
-- pg_cron installs cleanly — the procedure still exists and can be run by hand.
DO $reaper$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_available_extensions WHERE name = 'pg_cron') THEN
        CREATE EXTENSION IF NOT EXISTS pg_cron;

        -- Idempotent (re)schedule: drop any prior job of this name first.
        PERFORM cron.unschedule(jobid)
        FROM cron.job
        WHERE jobname = 'lti-ephemeral-reaper';

        PERFORM cron.schedule(
            'lti-ephemeral-reaper',
            '*/10 * * * *',
            'SELECT public.reap_lti_ephemeral();'
        );
    ELSE
        RAISE NOTICE 'pg_cron not available; reap_lti_ephemeral() created but NOT scheduled (local dev). Prod schedules it.';
    END IF;
END
$reaper$;
