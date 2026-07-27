-- Add an `is_lti_user` boolean to the JWT custom claims.
--
-- WHY: Schoology-embedded (LTI) users must get a locked, analytics-only
-- experience (dashboard + reports, no settings/account). Enforcing that in the
-- UI shell, in Next.js middleware, and in the FastAPI account-mutation
-- endpoints needs ONE signed, uniform signal available to all three layers.
-- The JWT is that single source of truth.
--
-- The claim is derived from the DURABLE identity fact — the existence of an
-- `lti_user_identity` row for the user — NOT from the synthetic `@lti.local`
-- email string. Keying authorization on the email convention would silently
-- fail OPEN (LTI users would regain settings access) if the synthetic domain
-- were ever renamed; deriving from the identity row cannot.
--
-- Strictly ADDITIVE: this CREATE OR REPLACE reproduces the current hook body
-- (from 20260718120000_hierarchy_rank_inversion.sql) verbatim and only adds the
-- new claim. Existing claims (user_role, permissions, hierarchy_rank,
-- school_ids, primary_school_id, is_super_admin) are unchanged. CREATE OR
-- REPLACE preserves the function's existing GRANTs, so no re-grant is needed.

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
    hierarchy_rank    INTEGER;
    school_ids        TEXT[];
    primary_school_id TEXT;
    is_super_admin    BOOLEAN;
    is_lti_user       BOOLEAN;
BEGIN
    uid := (event->>'user_id')::UUID;

    SELECT r.name INTO user_role
    FROM public.user_roles ur
    JOIN public.roles r ON r.id = ur.role_id
    WHERE ur.user_id = uid
    ORDER BY r.hierarchy_rank ASC
    LIMIT 1;

    SELECT ARRAY_AGG(DISTINCT p.module || ':' || p.action)
    INTO user_permissions
    FROM public.user_roles ur
    JOIN public.role_permissions rp ON rp.role_id = ur.role_id
    JOIN public.permissions p ON p.id = rp.permission_id
    WHERE ur.user_id = uid;

    SELECT COALESCE(MIN(r.hierarchy_rank), 2147483647)
    INTO hierarchy_rank
    FROM public.user_roles ur
    JOIN public.roles r ON r.id = ur.role_id
    WHERE ur.user_id = uid;

    SELECT ARRAY_AGG(us.school_id::TEXT)
    INTO school_ids
    FROM public.user_schools us
    WHERE us.user_id = uid;

    SELECT us.school_id::TEXT
    INTO primary_school_id
    FROM public.user_schools us
    WHERE us.user_id = uid AND us.is_primary
    LIMIT 1;

    IF primary_school_id IS NULL THEN
        SELECT us.school_id::TEXT
        INTO primary_school_id
        FROM public.user_schools us
        WHERE us.user_id = uid
        ORDER BY us.created_at
        LIMIT 1;
    END IF;

    is_super_admin := COALESCE(user_role = 'super_admin', FALSE);

    -- Durable LTI-identity signal: a row exists iff this user was provisioned
    -- via an LTI launch (see lti_service.provision).
    SELECT EXISTS (
        SELECT 1 FROM public.lti_user_identity WHERE user_id = uid
    ) INTO is_lti_user;

    event := jsonb_set(event, '{claims,user_role}', to_jsonb(COALESCE(user_role, 'user')));
    event := jsonb_set(event, '{claims,permissions}', to_jsonb(COALESCE(user_permissions, ARRAY[]::TEXT[])));
    event := jsonb_set(event, '{claims,hierarchy_rank}', to_jsonb(hierarchy_rank));
    event := jsonb_set(event, '{claims,school_ids}', to_jsonb(COALESCE(school_ids, ARRAY[]::TEXT[])));
    event := jsonb_set(event, '{claims,primary_school_id}',
                       COALESCE(to_jsonb(primary_school_id), 'null'::jsonb));
    event := jsonb_set(event, '{claims,is_super_admin}', to_jsonb(is_super_admin));
    event := jsonb_set(event, '{claims,is_lti_user}', to_jsonb(COALESCE(is_lti_user, FALSE)));

    RETURN event;
END;
$$;
