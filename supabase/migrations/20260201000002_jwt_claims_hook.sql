-- ==============================================
-- JWT Custom Claims Hook
-- Injects role and permissions into JWT
-- No helper functions - queries database directly
-- ==============================================

-- Custom Access Token Hook
CREATE OR REPLACE FUNCTION public.custom_access_token_hook(event JSONB)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    user_role TEXT;
    user_permissions TEXT[];
    hierarchy_level INTEGER;
BEGIN
    -- Get user's highest role (by hierarchy level)
    SELECT r.name INTO user_role
    FROM public.user_roles ur
    JOIN public.roles r ON r.id = ur.role_id
    WHERE ur.user_id = (event->>'user_id')::UUID
    ORDER BY r.hierarchy_level DESC
    LIMIT 1;

    -- Get all user's permissions (aggregated from all their roles)
    SELECT ARRAY_AGG(DISTINCT p.module || ':' || p.action)
    INTO user_permissions
    FROM public.user_roles ur
    JOIN public.role_permissions rp ON rp.role_id = ur.role_id
    JOIN public.permissions p ON p.id = rp.permission_id
    WHERE ur.user_id = (event->>'user_id')::UUID;

    -- Get user's highest hierarchy level
    SELECT COALESCE(MAX(r.hierarchy_level), 0)
    INTO hierarchy_level
    FROM public.user_roles ur
    JOIN public.roles r ON r.id = ur.role_id
    WHERE ur.user_id = (event->>'user_id')::UUID;

    -- Inject claims into JWT
    event := jsonb_set(event, '{claims,user_role}', to_jsonb(COALESCE(user_role, 'user')));
    event := jsonb_set(event, '{claims,permissions}', to_jsonb(COALESCE(user_permissions, ARRAY[]::TEXT[])));
    event := jsonb_set(event, '{claims,hierarchy_level}', to_jsonb(hierarchy_level));

    RETURN event;
END;
$$;

-- Grant execute permission
GRANT EXECUTE ON FUNCTION public.custom_access_token_hook TO supabase_auth_admin;
REVOKE EXECUTE ON FUNCTION public.custom_access_token_hook FROM authenticated, anon, public;
