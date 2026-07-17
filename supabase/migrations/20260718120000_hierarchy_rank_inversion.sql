-- ============================================================================
-- Role hierarchy: invert to an ordinal RANK where LOWER = more senior.
-- ============================================================================
-- Old model: roles.hierarchy_level, HIGHER = more senior (super_admin=10000,
--            user=100, customs in a gapped band).
-- New model: roles.hierarchy_rank, LOWER = more senior:
--            super_admin = 0 (pinned), custom roles contiguous 1..N (1 = most
--            senior custom), user = 100000 (pinned, always junior to customs).
--            A user's effective rank = MIN(rank); an actor may manage a target
--            only when the target's rank is STRICTLY GREATER (more junior).
--
-- The column is RENAMED (not just re-valued) so any application code that still
-- references the old name fails loudly instead of comparing in the wrong
-- direction. The JWT hook now emits a `hierarchy_rank` claim (the old
-- `hierarchy_level` claim disappears — stale tokens read as most-junior,
-- fail-closed).
--
-- Additive + idempotent + transactional. The renumber runs with the
-- system-role protection trigger disabled INSIDE this transaction only (auto
-- re-enabled on rollback). Migrations run as the table owner, so DISABLE is
-- permitted.
--
-- ⚠️ Prod auto-migrates on main-push: this migration MUST merge in the SAME PR
-- as the backend/frontend code that understands the new semantics.
-- ============================================================================

-- 1. Rename the column (DDL; triggers don't fire; the CHECK follows the rename).
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'roles'
          AND column_name = 'hierarchy_level'
    ) THEN
        ALTER TABLE public.roles RENAME COLUMN hierarchy_level TO hierarchy_rank;
    END IF;
END $$;

-- 2. Drop the old DEFAULT (0 now means super_admin — never a safe default).
ALTER TABLE public.roles ALTER COLUMN hierarchy_rank DROP DEFAULT;

-- 3. Rename the CHECK constraint for hygiene (predicate unchanged: >= 0).
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'valid_hierarchy_level'
          AND conrelid = 'public.roles'::regclass
    ) THEN
        ALTER TABLE public.roles
            RENAME CONSTRAINT valid_hierarchy_level TO valid_hierarchy_rank;
    END IF;
END $$;

-- 4. Re-create the system-role protection to reference hierarchy_rank.
CREATE OR REPLACE FUNCTION public.protect_system_roles()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'UPDATE' AND OLD.is_system = TRUE THEN
        IF NEW.name != OLD.name THEN
            RAISE EXCEPTION 'Cannot modify system role name: %', OLD.name;
        END IF;
        IF NEW.hierarchy_rank != OLD.hierarchy_rank THEN
            RAISE EXCEPTION 'Cannot modify system role hierarchy: %', OLD.name;
        END IF;
        IF NEW.is_system != OLD.is_system THEN
            RAISE EXCEPTION 'Cannot change is_system flag for role: %', OLD.name;
        END IF;
    END IF;

    IF TG_OP = 'DELETE' AND OLD.is_system = TRUE THEN
        RAISE EXCEPTION 'Cannot delete system role: %', OLD.name;
    END IF;

    RETURN COALESCE(NEW, OLD);
END;
$$ LANGUAGE plpgsql;

-- 5. Renumber to the new scheme, with the protection trigger disabled for the
--    duration of this transaction only. Idempotent: the ordering direction is
--    chosen from super_admin's current value so re-applying is a no-op.
DO $$
DECLARE
    old_super_rank INTEGER;
    dir TEXT;
BEGIN
    ALTER TABLE public.roles DISABLE TRIGGER enforce_system_role_protection;

    SELECT hierarchy_rank INTO old_super_rank
    FROM public.roles WHERE name = 'super_admin';

    -- Pre-inversion super is the MAX (e.g. 10000) → customs seniority-first = DESC.
    -- Post-inversion super is 0 → customs already ascending seniority-first = ASC.
    dir := CASE WHEN COALESCE(old_super_rank, 0) > 0 THEN 'DESC' ELSE 'ASC' END;

    UPDATE public.roles SET hierarchy_rank = 0
        WHERE name = 'super_admin' AND hierarchy_rank <> 0;
    UPDATE public.roles SET hierarchy_rank = 100000
        WHERE name = 'user' AND hierarchy_rank <> 100000;

    EXECUTE format($f$
        UPDATE public.roles r SET hierarchy_rank = t.rn
        FROM (
            SELECT id, ROW_NUMBER() OVER (ORDER BY hierarchy_rank %s) AS rn
            FROM public.roles WHERE is_system = FALSE
        ) t
        WHERE r.id = t.id AND r.hierarchy_rank <> t.rn
    $f$, dir);

    ALTER TABLE public.roles ENABLE TRIGGER enforce_system_role_protection;
END $$;

-- 6. Re-create the JWT claims hook: name/rank now come from the MOST SENIOR
--    (minimum-rank) role; the rank claim is MIN(...) with a most-junior sentinel;
--    the claim key is renamed to `hierarchy_rank`.
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
BEGIN
    uid := (event->>'user_id')::UUID;

    -- Most senior role = lowest rank.
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

    -- Effective rank = MIN over the user's roles; no roles = most junior.
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

    event := jsonb_set(event, '{claims,user_role}', to_jsonb(COALESCE(user_role, 'user')));
    event := jsonb_set(event, '{claims,permissions}', to_jsonb(COALESCE(user_permissions, ARRAY[]::TEXT[])));
    event := jsonb_set(event, '{claims,hierarchy_rank}', to_jsonb(hierarchy_rank));
    event := jsonb_set(event, '{claims,school_ids}', to_jsonb(COALESCE(school_ids, ARRAY[]::TEXT[])));
    event := jsonb_set(event, '{claims,primary_school_id}',
                       COALESCE(to_jsonb(primary_school_id), 'null'::jsonb));
    event := jsonb_set(event, '{claims,is_super_admin}', to_jsonb(is_super_admin));

    RETURN event;
END;
$$;

GRANT EXECUTE ON FUNCTION public.custom_access_token_hook TO supabase_auth_admin;
REVOKE EXECUTE ON FUNCTION public.custom_access_token_hook FROM authenticated, anon, public;
