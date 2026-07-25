-- ============================================================================
-- LTI 1.3 session handoff ticket
-- ============================================================================
-- Single-use, short-lived (60s) ticket that bridges a verified LTI launch into
-- a real Supabase session. FastAPI's /lti/launch mints one row after
-- provisioning the user; the Next.js /api/lti/bridge route consumes it (via the
-- machine-auth /lti/consume-ticket endpoint) and mints a magic-link session for
-- the carried email. school_id travels in the row so the bridge can scope the
-- final redirect to the right tenant.
--
-- Managed only by FastAPI as service_role (same rationale as the other LTI
-- tables — see 20260601000020_lti.sql:64-65). No tenant RLS: this is
-- infrastructure, not tenant data, and the machine-auth path has no user JWT.
-- ============================================================================

CREATE TABLE public.lti_handoff_ticket (
  id         UUID PRIMARY KEY DEFAULT uuid_generate_v7(),
  ticket     TEXT NOT NULL UNIQUE,
  user_id    UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  school_id  UUID REFERENCES public.schools(school_id) ON DELETE SET NULL,
  email      TEXT NOT NULL,
  consumed   BOOLEAN NOT NULL DEFAULT FALSE,
  expires_at TIMESTAMPTZ NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX lti_handoff_ticket_ticket_idx ON public.lti_handoff_ticket (ticket);

COMMENT ON TABLE public.lti_handoff_ticket IS
  'FastAPI/service_role-managed single-use LTI session handoff tickets. No tenant RLS (infrastructure, machine-auth path — matches the other lti_* tables).';
