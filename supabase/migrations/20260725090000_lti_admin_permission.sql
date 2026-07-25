-- Wave 2 — admin-dynamic LTI management.
-- New permission gating the per-school LTI binding admin endpoints
-- (/api/v1/admin/lti/*). The permissions table uses (module, action) UNIQUE;
-- the on_permission_created trigger grants every new row to super_admin, so
-- this INSERT alone makes super_admin able to manage LTI bindings.
INSERT INTO public.permissions (module, action, description) VALUES
    ('schools', 'manage_lti', 'Manage LTI 1.3 registrations and deployment bindings')
ON CONFLICT (module, action) DO NOTHING;
