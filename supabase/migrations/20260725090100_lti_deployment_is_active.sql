-- Wave 2 — per-school LTI enable flag.
-- A disabled deployment binding is the admin's fail-closed off-switch: the
-- launch path (_resolve_school) gates on `is_active`, so a disabled binding
-- resolves to NO school → RLS returns zero rows. Defaults TRUE so existing
-- bindings keep working unchanged.
ALTER TABLE public.lti_deployment
    ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT TRUE;
