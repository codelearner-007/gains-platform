-- ============================================================================
-- user_schools — links auth.users ⇄ schools (the multi-tenant membership table)
-- ============================================================================
-- This is the load-bearing control-plane table for multi-tenancy. Before it,
-- there was no relation between an authenticated user and a tenant, so every
-- non-super-admin silently resolved to Athenian (see middleware/rls.py).
--
-- Semantics:
--   * A user may belong to one OR more schools (a district admin could span
--     several; a teacher/student belongs to exactly one in practice).
--   * `school_role` is the user's role WITHIN that school (admin/teacher/
--     student). It is distinct from the platform RBAC role (super_admin/user):
--     platform super_admin = cross-tenant operator; school_role = in-tenant.
--   * `is_primary` marks the default school used when no explicit ?school_id is
--     supplied. Exactly one primary per user is enforced by a partial unique idx.
-- ============================================================================

CREATE TABLE IF NOT EXISTS public.user_schools (
  id          UUID PRIMARY KEY DEFAULT uuid_generate_v7(),
  user_id     UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  school_id   UUID NOT NULL REFERENCES public.schools(school_id) ON DELETE CASCADE,
  school_role TEXT NOT NULL DEFAULT 'member'
              CHECK (school_role IN ('admin', 'teacher', 'student', 'member')),
  is_primary  BOOLEAN NOT NULL DEFAULT FALSE,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (user_id, school_id)
);

CREATE INDEX user_schools_user_idx   ON public.user_schools (user_id);
CREATE INDEX user_schools_school_idx ON public.user_schools (school_id);

-- Exactly one primary school per user.
CREATE UNIQUE INDEX user_schools_one_primary_idx
  ON public.user_schools (user_id)
  WHERE is_primary;

-- ----------------------------------------------------------------------------
-- RLS: a user can read their own membership rows; service_role manages all.
-- (Membership writes happen via FastAPI as service_role behind an RBAC check.)
-- ----------------------------------------------------------------------------
ALTER TABLE public.user_schools ENABLE ROW LEVEL SECURITY;

CREATE POLICY user_schools_self_select ON public.user_schools
  FOR SELECT
  USING (auth.uid() = user_id);

CREATE POLICY user_schools_service_full ON public.user_schools
  FOR ALL TO service_role
  USING (true) WITH CHECK (true);

-- The JWT claims hook (supabase_auth_admin) must read this table.
GRANT SELECT ON public.user_schools TO supabase_auth_admin;
