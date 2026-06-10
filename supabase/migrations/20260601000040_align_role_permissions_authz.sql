-- ============================================================================
-- G7 — align role_permissions write authz with the API gate
-- ============================================================================
-- The role_permissions INSERT/DELETE RLS policies (20260201000001_rbac_system.sql)
-- gated writes on `i_have_permission('permissions','update')`, while the API
-- (POST/DELETE-equivalent: PUT /api/v1/roles/{id}/permissions in roles.py)
-- gates on `roles:update`. The backend connects as the service_role (RLS
-- bypass) so this divergence was latent, but it is a correctness/defense-in-
-- depth hazard: any future authenticated (non-service) write path would be
-- governed by a DIFFERENT permission than the documented API contract.
--
-- This migration realigns the RLS policies to `i_have_permission('roles',
-- 'update')` so the single source of truth for "who may change a role's
-- permission set" is `roles:update` — matching the API. This is NOT a
-- loosening: super_admin permission immutability + system-role protection are
-- enforced by the BEFORE-DELETE triggers `enforce_super_admin_permissions` and
-- `enforce_system_role_protection`, which are untouched here.
-- ============================================================================

DROP POLICY IF EXISTS "Admins can assign permissions to roles" ON public.role_permissions;
DROP POLICY IF EXISTS "Admins can remove permissions from roles" ON public.role_permissions;

CREATE POLICY "Admins can assign permissions to roles"
    ON public.role_permissions FOR INSERT
    WITH CHECK (public.i_have_permission('roles', 'update'));

CREATE POLICY "Admins can remove permissions from roles"
    ON public.role_permissions FOR DELETE
    USING (public.i_have_permission('roles', 'update'));
