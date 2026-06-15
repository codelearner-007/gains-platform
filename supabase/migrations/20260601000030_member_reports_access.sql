-- ============================================================================
-- Grant reports:read to the platform 'user' role.
-- ============================================================================
-- In the multi-tenant model, any authenticated school member (teacher/student)
-- views their OWN school's reports — RLS (app.current_school_id) scopes the
-- data, so read access is safe to grant broadly. Without this, members get
-- "You do not have access to this report" because the base 'user' role had no
-- permissions. Admin-only modules (users/rbac/audit/schools) remain gated by
-- their own permissions, which 'user' still lacks.
-- ============================================================================

INSERT INTO public.role_permissions (role_id, permission_id)
SELECT r.id, p.id
FROM public.roles r, public.permissions p
WHERE r.name = 'user'
  AND p.module = 'reports'
  AND p.action = 'read'
ON CONFLICT (role_id, permission_id) DO NOTHING;
