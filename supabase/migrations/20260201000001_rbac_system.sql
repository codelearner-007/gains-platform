-- ==============================================
-- RBAC System - Schema Only (No Seed Data)
-- Seed data is in supabase/seeds/*.sql
-- ==============================================

-- Note: UUID v7 function loaded from previous migration (20260201000000_uuid_v7_function.sql)
-- Using uuid_generate_v7() instead of uuid_generate_v7() for better performance

-- ==============================================
-- STEP 1: CREATE CORE TABLES
-- ==============================================

-- User Profiles
CREATE TABLE IF NOT EXISTS public.user_profiles (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v7(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    full_name TEXT,
    avatar_url TEXT,
    department TEXT,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    UNIQUE(user_id)
);

-- Roles Table
CREATE TABLE IF NOT EXISTS public.roles (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v7(),
    name TEXT NOT NULL UNIQUE,
    description TEXT,
    hierarchy_level INTEGER NOT NULL DEFAULT 0,
    is_system BOOLEAN DEFAULT FALSE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    CONSTRAINT valid_hierarchy_level CHECK (hierarchy_level >= 0)
);

-- Permissions Table (module:action format)
CREATE TABLE IF NOT EXISTS public.permissions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v7(),
    module TEXT NOT NULL,
    action TEXT NOT NULL,
    description TEXT,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    UNIQUE(module, action)
);

-- User Roles Junction
CREATE TABLE IF NOT EXISTS public.user_roles (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v7(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    role_id UUID NOT NULL REFERENCES public.roles(id) ON DELETE CASCADE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    UNIQUE(user_id, role_id)
);

-- Role Permissions Junction
CREATE TABLE IF NOT EXISTS public.role_permissions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v7(),
    role_id UUID NOT NULL REFERENCES public.roles(id) ON DELETE CASCADE,
    permission_id UUID NOT NULL REFERENCES public.permissions(id) ON DELETE CASCADE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    UNIQUE(role_id, permission_id)
);

-- Audit Logs
CREATE TABLE IF NOT EXISTS public.audit_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v7(),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    user_id UUID REFERENCES auth.users(id) ON DELETE SET NULL,
    action TEXT NOT NULL,
    module TEXT NOT NULL,
    resource_id TEXT,
    details JSONB,
    ip_address INET,
    user_agent TEXT
);

-- ==============================================
-- STEP 2: ESSENTIAL FUNCTIONS ONLY
-- ==============================================

-- Auto-update timestamp trigger function
CREATE OR REPLACE FUNCTION public.handle_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Protect system roles from modification
CREATE OR REPLACE FUNCTION public.protect_system_roles()
RETURNS TRIGGER AS $$
BEGIN
    -- Prevent UPDATE of system roles (except description)
    IF TG_OP = 'UPDATE' AND OLD.is_system = TRUE THEN
        IF NEW.name != OLD.name THEN
            RAISE EXCEPTION 'Cannot modify system role name: %', OLD.name;
        END IF;
        IF NEW.hierarchy_level != OLD.hierarchy_level THEN
            RAISE EXCEPTION 'Cannot modify system role hierarchy: %', OLD.name;
        END IF;
        IF NEW.is_system != OLD.is_system THEN
            RAISE EXCEPTION 'Cannot change is_system flag for role: %', OLD.name;
        END IF;
        -- Allow description updates only
    END IF;

    -- Prevent DELETE of system roles
    IF TG_OP = 'DELETE' AND OLD.is_system = TRUE THEN
        RAISE EXCEPTION 'Cannot delete system role: %', OLD.name;
    END IF;

    RETURN COALESCE(NEW, OLD);
END;
$$ LANGUAGE plpgsql;

-- Prevent removing permissions from super_admin
CREATE OR REPLACE FUNCTION public.protect_super_admin_permissions()
RETURNS TRIGGER AS $$
DECLARE
    role_name TEXT;
BEGIN
    -- Get role name
    SELECT r.name INTO role_name
    FROM public.roles r
    WHERE r.id = OLD.role_id;

    -- Block deletion of super_admin permissions
    IF TG_OP = 'DELETE' AND role_name = 'super_admin' THEN
        RAISE EXCEPTION 'Cannot remove permissions from super_admin role';
    END IF;

    RETURN OLD;
END;
$$ LANGUAGE plpgsql;

-- Check permission from JWT (used in RLS policies)
-- This is the ONLY permission check function - queries JWT claims, not database
CREATE OR REPLACE FUNCTION public.i_have_permission(module_name TEXT, action_name TEXT)
RETURNS BOOLEAN AS $$
DECLARE
    my_permissions TEXT[];
    check_permission TEXT;
BEGIN
    -- Extract permissions array from JWT claims
    SELECT ARRAY(
        SELECT jsonb_array_elements_text(
            COALESCE(
                NULLIF(current_setting('request.jwt.claims', true), '')::jsonb->'permissions',
                '[]'::jsonb
            )
        )
    ) INTO my_permissions;

    check_permission := module_name || ':' || action_name;
    RETURN check_permission = ANY(my_permissions);
END;
$$ LANGUAGE plpgsql STABLE;

-- ==============================================
-- STEP 3: AUTO-ASSIGNMENT TRIGGERS
-- ==============================================

-- Auto-assign new permissions to super_admin
-- When a new permission is created, automatically grant it to super_admin
CREATE OR REPLACE FUNCTION public.auto_assign_permission_to_super_admin()
RETURNS TRIGGER AS $$
DECLARE
    super_admin_role_id UUID;
BEGIN
    -- Get super_admin role id
    SELECT id INTO super_admin_role_id
    FROM public.roles
    WHERE name = 'super_admin';

    -- If super_admin role exists, assign this new permission to it
    IF super_admin_role_id IS NOT NULL THEN
        INSERT INTO public.role_permissions (role_id, permission_id)
        VALUES (super_admin_role_id, NEW.id)
        ON CONFLICT (role_id, permission_id) DO NOTHING;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Trigger: Auto-assign new permissions to super_admin
DROP TRIGGER IF EXISTS on_permission_created ON public.permissions;
CREATE TRIGGER on_permission_created
    AFTER INSERT ON public.permissions
    FOR EACH ROW
    EXECUTE FUNCTION public.auto_assign_permission_to_super_admin();

-- Trigger: Protect system roles
CREATE TRIGGER enforce_system_role_protection
    BEFORE UPDATE OR DELETE ON public.roles
    FOR EACH ROW
    EXECUTE FUNCTION public.protect_system_roles();

-- Trigger: Protect super_admin permissions
CREATE TRIGGER enforce_super_admin_permissions
    BEFORE DELETE ON public.role_permissions
    FOR EACH ROW
    EXECUTE FUNCTION public.protect_super_admin_permissions();

-- ==============================================
-- STEP 4: FIRST USER IS SUPER ADMIN
-- ==============================================

-- Handle new user registration
-- STRICT RULE: First user (and ONLY first user) becomes super_admin
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER AS $$
DECLARE
    target_role_id UUID;
    existing_super_admin_count INTEGER;
BEGIN
    -- Create user profile
    INSERT INTO public.user_profiles (user_id, full_name)
    VALUES (NEW.id, NEW.raw_user_meta_data->>'full_name');

    -- Advisory lock to serialize first-user check (prevents race condition)
    -- Lock ID: 1234567890 (arbitrary constant for super_admin assignment)
    PERFORM pg_advisory_xact_lock(1234567890);

    -- Check if super_admin role is already assigned to any user
    SELECT COUNT(*) INTO existing_super_admin_count
    FROM public.user_roles ur
    JOIN public.roles r ON r.id = ur.role_id
    WHERE r.name = 'super_admin';

    -- First user becomes super_admin, all others become regular user
    IF existing_super_admin_count = 0 THEN
        -- This is the FIRST user - make them super_admin
        SELECT id INTO target_role_id
        FROM public.roles
        WHERE name = 'super_admin';

        RAISE NOTICE 'First user detected - assigning super_admin role';
    ELSE
        -- All subsequent users get 'user' role
        SELECT id INTO target_role_id
        FROM public.roles
        WHERE name = 'user';
    END IF;

    -- Assign the role
    IF target_role_id IS NOT NULL THEN
        INSERT INTO public.user_roles (user_id, role_id)
        VALUES (NEW.id, target_role_id);
    END IF;

    -- Lock automatically released at transaction commit
    RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Trigger: Auto-assign role on user creation
DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
CREATE TRIGGER on_auth_user_created
    AFTER INSERT ON auth.users
    FOR EACH ROW
    EXECUTE FUNCTION public.handle_new_user();

-- ==============================================
-- STEP 4.5: PREVENT MANUAL SUPER ADMIN ASSIGNMENT
-- ==============================================

-- Prevent manual assignment of super_admin role
-- Only service_role (backend), postgres, or supabase_admin can assign it
-- Regular authenticated/anon users cannot assign super_admin directly
CREATE OR REPLACE FUNCTION public.prevent_super_admin_manual_assignment()
RETURNS TRIGGER AS $$
DECLARE
    role_name_val TEXT;
BEGIN
    -- Get the role name being assigned
    SELECT r.name INTO role_name_val
    FROM public.roles r
    WHERE r.id = NEW.role_id;

    -- Prevent direct super_admin assignment by end-user roles
    IF role_name_val = 'super_admin' THEN
        -- Only block authenticated/anon (end-user) sessions
        -- All server-side roles (postgres, supabase_auth_admin, service_role, etc.) are allowed
        IF session_user IN ('authenticated', 'anon') THEN
            RAISE EXCEPTION 'Super admin role cannot be assigned directly. Use the admin API.';
        END IF;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

DROP TRIGGER IF EXISTS prevent_manual_super_admin_assignment ON public.user_roles;
CREATE TRIGGER prevent_manual_super_admin_assignment
    BEFORE INSERT ON public.user_roles
    FOR EACH ROW
    EXECUTE FUNCTION public.prevent_super_admin_manual_assignment();

-- ==============================================
-- STEP 5: ENABLE RLS
-- ==============================================
ALTER TABLE public.user_profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.roles ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.permissions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.user_roles ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.role_permissions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.audit_logs ENABLE ROW LEVEL SECURITY;

-- ==============================================
-- STEP 6: CREATE RLS POLICIES
-- ==============================================

-- User Profiles
CREATE POLICY "Users can view own profile"
    ON public.user_profiles FOR SELECT
    USING (auth.uid() = user_id);

CREATE POLICY "Users can update own profile"
    ON public.user_profiles FOR UPDATE
    USING (auth.uid() = user_id);

CREATE POLICY "Admins can view all profiles"
    ON public.user_profiles FOR SELECT
    USING (public.i_have_permission('users', 'read_all'));

CREATE POLICY "Admins can update all profiles"
    ON public.user_profiles FOR UPDATE
    USING (public.i_have_permission('users', 'update_all'));

CREATE POLICY "Admins can delete profiles"
    ON public.user_profiles FOR DELETE
    USING (public.i_have_permission('users', 'delete_all'));

-- ========== Roles RLS Policies ==========
CREATE POLICY "Anyone can view roles"
    ON public.roles FOR SELECT
    USING (true);

CREATE POLICY "Admins can create roles"
    ON public.roles FOR INSERT
    WITH CHECK (public.i_have_permission('roles', 'create'));

CREATE POLICY "Admins can update roles"
    ON public.roles FOR UPDATE
    USING (public.i_have_permission('roles', 'update'))
    WITH CHECK (public.i_have_permission('roles', 'update'));

CREATE POLICY "Admins can delete roles"
    ON public.roles FOR DELETE
    USING (public.i_have_permission('roles', 'delete'));

-- ========== Permissions RLS Policies ==========
CREATE POLICY "Anyone can view permissions"
    ON public.permissions FOR SELECT
    USING (true);

CREATE POLICY "Admins can create permissions"
    ON public.permissions FOR INSERT
    WITH CHECK (public.i_have_permission('permissions', 'create'));

CREATE POLICY "Admins can update permissions"
    ON public.permissions FOR UPDATE
    USING (public.i_have_permission('permissions', 'update'))
    WITH CHECK (public.i_have_permission('permissions', 'update'));

CREATE POLICY "Admins can delete permissions"
    ON public.permissions FOR DELETE
    USING (public.i_have_permission('permissions', 'delete'));

-- User Roles
CREATE POLICY "Users can view own roles"
    ON public.user_roles FOR SELECT
    USING (auth.uid() = user_id);

CREATE POLICY "Admins can manage user roles"
    ON public.user_roles FOR ALL
    USING (public.i_have_permission('users', 'assign_roles'));

-- ========== Role Permissions RLS Policies ==========
CREATE POLICY "Anyone can view role permissions"
    ON public.role_permissions FOR SELECT
    USING (true);

CREATE POLICY "Admins can assign permissions to roles"
    ON public.role_permissions FOR INSERT
    WITH CHECK (public.i_have_permission('permissions', 'update'));

CREATE POLICY "Admins can remove permissions from roles"
    ON public.role_permissions FOR DELETE
    USING (public.i_have_permission('permissions', 'update'));

-- Audit Logs (admin read; service_role only writes)
CREATE POLICY "Admins can view audit logs"
    ON public.audit_logs FOR SELECT
    USING (public.i_have_permission('audit', 'read'));

-- Backend (FastAPI) uses the service_role bypass — no INSERT policy is needed for it.
-- Authenticated users intentionally cannot write audit logs to prevent tampering.

-- ==============================================
-- STEP 7: TIMESTAMP TRIGGERS
-- ==============================================
CREATE TRIGGER set_updated_at_user_profiles
    BEFORE UPDATE ON public.user_profiles
    FOR EACH ROW
    EXECUTE FUNCTION public.handle_updated_at();

CREATE TRIGGER set_updated_at_roles
    BEFORE UPDATE ON public.roles
    FOR EACH ROW
    EXECUTE FUNCTION public.handle_updated_at();

-- ==============================================
-- STEP 8: GRANTS (Principle of Least Privilege)
-- ==============================================

-- Schema usage for authenticated users only
GRANT USAGE ON SCHEMA public TO authenticated;

-- Authenticated users: read-only on reference tables and audit logs.
GRANT SELECT ON public.user_profiles, public.roles, public.permissions, public.role_permissions, public.user_roles TO authenticated;
GRANT SELECT ON public.audit_logs TO authenticated;

-- Grant execute on public functions needed for RLS policy evaluation
GRANT EXECUTE ON FUNCTION public.i_have_permission(TEXT, TEXT) TO authenticated;

-- Anon users: NO access to application tables
-- (Supabase handles auth schema access for anon automatically)

-- Service role (used by FastAPI backend) needs full CRUD on all tables
GRANT ALL ON ALL TABLES IN SCHEMA public TO service_role;
GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO service_role;

-- ==============================================
-- STEP 9: SEED SYSTEM ROLES (idempotent — safe to re-run)
-- ==============================================
-- These roles are required by handle_new_user() for new sign-ups, so they
-- must exist before any user is created. Defined here (instead of in seeds/)
-- so production deploys via `supabase db push` work without an extra seed step.
INSERT INTO public.roles (name, description, hierarchy_level, is_system) VALUES
    ('super_admin', 'Super Administrator with full system access', 10000, TRUE),
    ('user', 'Regular user with basic permissions', 100, TRUE)
ON CONFLICT (name) DO UPDATE SET is_system = EXCLUDED.is_system;

-- ==============================================
-- NOTE: Permissions seed is in supabase/seeds/rbac_seed.sql
-- (perm rows can grow over time; roles are foundational and live with the schema)
-- ==============================================
