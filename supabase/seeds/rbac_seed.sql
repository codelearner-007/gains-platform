-- ==============================================
-- RBAC SEED DATA — Permissions only.
-- System roles (super_admin, user) are seeded by the rbac_system migration so
-- they exist on every deploy (including `supabase db push` without seed run).
-- ==============================================

INSERT INTO public.permissions (module, action, description) VALUES
    -- Users module
    ('users', 'read_all', 'View all users'),
    ('users', 'update_all', 'Update all users'),
    ('users', 'delete_all', 'Delete users'),
    ('users', 'assign_roles', 'Assign roles to users'),

    -- Roles module
    ('roles', 'create', 'Create new roles'),
    ('roles', 'read', 'View roles'),
    ('roles', 'update', 'Update roles'),
    ('roles', 'delete', 'Delete roles'),

    -- Permissions module
    ('permissions', 'create', 'Create new permissions'),
    ('permissions', 'read', 'View permissions'),
    ('permissions', 'update', 'Update permissions'),
    ('permissions', 'delete', 'Delete permissions'),

    -- Audit module
    ('audit', 'read', 'View audit logs')
ON CONFLICT (module, action) DO NOTHING;

-- Super admin gets all current + future permissions (auto_assign trigger covers future).
INSERT INTO public.role_permissions (role_id, permission_id)
SELECT r.id, p.id
FROM public.roles r
CROSS JOIN public.permissions p
WHERE r.name = 'super_admin'
ON CONFLICT (role_id, permission_id) DO NOTHING;
