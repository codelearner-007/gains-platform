-- Phase 5 — Report and admin permissions for the Gains pipeline.
-- The permissions table uses (module, action) UNIQUE; the auto_assign trigger
-- on permissions inserts grants every new row to the super_admin role.

INSERT INTO public.permissions (module, action, description) VALUES
    ('reports',   'read',       'View reports'),
    ('schools',   'create',     'Create schools'),
    ('schools',   'update',     'Update schools'),
    ('schools',   'read_all',   'List all schools (admin)'),
    ('ingestion', 'trigger',    'Trigger ingestion runs'),
    ('ingestion', 'read',       'View ingestion run history')
ON CONFLICT (module, action) DO NOTHING;
