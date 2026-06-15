-- ============================================================================
-- JWT Custom Claims Hook — add school membership claims
-- ============================================================================
-- Extends custom_access_token_hook (originally in 20260201000002) to inject the
-- caller's school membership so the backend can resolve tenant context from the
-- token instead of the Athenian fallback:
--
--   claims.school_ids        TEXT[]  — every school_id the user belongs to
--   claims.primary_school_id TEXT    — the user's default school (is_primary)
--   claims.is_super_admin    BOOLEAN — cross-tenant operator (platform role)
--
-- super_admins are cross-tenant: they carry is_super_admin=true and are NOT
-- restricted to their school_ids by the backend (they scope via ?school_id).
-- ============================================================================

CREATE OR REPLACE FUNCTION public.custom_access_token_hook(event JSONB)
RETURNS JSONB
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    uid               UUID;
    user_role         TEXT;
    user_permissions  TEXT[];
    hierarchy_level   INTEGER;
    school_ids        TEXT[];
    primary_school_id TEXT;
    is_super_admin    BOOLEAN;
BEGIN
    uid := (event->>'user_id')::UUID;

    -- Highest role by hierarchy.
    SELECT r.name INTO user_role
    FROM public.user_roles ur
    JOIN public.roles r ON r.id = ur.role_id
    WHERE ur.user_id = uid
    ORDER BY r.hierarchy_level DESC
    LIMIT 1;

    -- All permissions aggregated across the user's roles.
    SELECT ARRAY_AGG(DISTINCT p.module || ':' || p.action)
    INTO user_permissions
    FROM public.user_roles ur
    JOIN public.role_permissions rp ON rp.role_id = ur.role_id
    JOIN public.permissions p ON p.id = rp.permission_id
    WHERE ur.user_id = uid;

    SELECT COALESCE(MAX(r.hierarchy_level), 0)
    INTO hierarchy_level
    FROM public.user_roles ur
    JOIN public.roles r ON r.id = ur.role_id
    WHERE ur.user_id = uid;

    -- School membership.
    SELECT ARRAY_AGG(us.school_id::TEXT)
    INTO school_ids
    FROM public.user_schools us
    WHERE us.user_id = uid;

    SELECT us.school_id::TEXT
    INTO primary_school_id
    FROM public.user_schools us
    WHERE us.user_id = uid AND us.is_primary
    LIMIT 1;

    -- Fall back to any membership as the primary if none flagged.
    IF primary_school_id IS NULL THEN
        SELECT us.school_id::TEXT
        INTO primary_school_id
        FROM public.user_schools us
        WHERE us.user_id = uid
        ORDER BY us.created_at
        LIMIT 1;
    END IF;

    is_super_admin := COALESCE(user_role = 'super_admin', FALSE);

    -- Inject claims.
    event := jsonb_set(event, '{claims,user_role}', to_jsonb(COALESCE(user_role, 'user')));
    event := jsonb_set(event, '{claims,permissions}', to_jsonb(COALESCE(user_permissions, ARRAY[]::TEXT[])));
    event := jsonb_set(event, '{claims,hierarchy_level}', to_jsonb(hierarchy_level));
    event := jsonb_set(event, '{claims,school_ids}', to_jsonb(COALESCE(school_ids, ARRAY[]::TEXT[])));
    -- to_jsonb(NULL) is SQL NULL, and jsonb_set(_, _, NULL) returns NULL — which
    -- would null out the entire token. Coalesce to a JSON null instead so a
    -- super-admin with no membership still gets a valid claims object.
    event := jsonb_set(event, '{claims,primary_school_id}',
                       COALESCE(to_jsonb(primary_school_id), 'null'::jsonb));
    event := jsonb_set(event, '{claims,is_super_admin}', to_jsonb(is_super_admin));

    RETURN event;
END;
$$;

GRANT EXECUTE ON FUNCTION public.custom_access_token_hook TO supabase_auth_admin;
REVOKE EXECUTE ON FUNCTION public.custom_access_token_hook FROM authenticated, anon, public;
