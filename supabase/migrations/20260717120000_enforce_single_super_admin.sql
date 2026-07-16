-- Enforce that at most ONE user ever holds the super_admin role.
--
-- Existing protections already: (a) auto-assign super_admin only to the first
-- user (handle_new_user), and (b) block authenticated/anon sessions from
-- assigning it directly (prevent_super_admin_manual_assignment). This closes
-- the remaining gap: a server-side role (postgres / service_role, i.e. the
-- backend) could still INSERT a SECOND super_admin. This trigger rejects any
-- super_admin assignment when a DIFFERENT user already holds it — regardless of
-- the connecting role.
--
-- Additive + idempotent: safe to re-run. Does not touch existing rows.

CREATE OR REPLACE FUNCTION public.enforce_single_super_admin()
RETURNS TRIGGER AS $$
DECLARE
    is_super BOOLEAN;
    existing_count INTEGER;
BEGIN
    SELECT (r.name = 'super_admin') INTO is_super
    FROM public.roles r
    WHERE r.id = NEW.role_id;

    IF COALESCE(is_super, FALSE) THEN
        SELECT COUNT(*) INTO existing_count
        FROM public.user_roles ur
        JOIN public.roles r ON r.id = ur.role_id
        WHERE r.name = 'super_admin'
          AND ur.user_id <> NEW.user_id;

        IF existing_count > 0 THEN
            RAISE EXCEPTION 'Only one super_admin is permitted on this platform.';
        END IF;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

DROP TRIGGER IF EXISTS enforce_single_super_admin ON public.user_roles;
CREATE TRIGGER enforce_single_super_admin
    BEFORE INSERT ON public.user_roles
    FOR EACH ROW
    EXECUTE FUNCTION public.enforce_single_super_admin();
