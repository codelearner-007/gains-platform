-- Historic-data LOCK CORE (MASTER_PLAN §LOCK, layer 3: DB backstop).
--
-- ADDITIVE + IDEMPOTENT + PROD-INERT. This migration introduces a single new
-- table (`locked_sessions`) and a BEFORE DELETE / BEFORE TRUNCATE trigger on
-- `fact_student_submission`. The whole mechanism is a NO-OP until an operator
-- explicitly inserts a lock row.
--
-- WHY: once a (school_id, session) year has been finalized, synced to prod, and
-- golden-verified, we never want ANYTHING — a re-run of the legacy full-rebuild
-- pipeline, a stray scoped DELETE, or a hand-typed `psql TRUNCATE` — to erase or
-- mutate that frozen slice. The DB itself is the last line of defense because it
-- fires no matter who or what issues the statement.
--
-- CRUCIAL INERTNESS CONTRACT: while `locked_sessions` is EMPTY the trigger is a
-- pure pass-through. The normal full-rebuild `TRUNCATE fact_student_submission`
-- and every existing test MUST keep working unchanged. Only a non-empty
-- `locked_sessions` arms the backstop.
--
-- ⚠️ PROD INVARIANT — NEVER INSERT A LOCK ROW FOR A PROD SESSION.
-- This migration auto-applies to prod on merge, but the lock is a LOCAL-REBUILD-
-- MACHINE safety, NOT a prod safety. On prod `locked_sessions` MUST stay
-- permanently empty. Prod's historic protection is layered elsewhere:
--   (1) prod never runs transforms (INGESTION_TRANSFORMS_ENABLED=false),
--   (2) every prod change goes through the gated Method-A sync (runbook 03), and
--   (3) that sync runs under `SET session_replication_role=replica`, which skips
--       origin-mode triggers — so these triggers never even fire during a resync.
-- If a prod session were ever locked, protection (1) still holds via the empty
-- floor and (3) still lets the resync through, BUT the double-guarantee degrades
-- to suspenders-only. Locking a prod session would also block any FUTURE resync
-- path that did NOT use replica mode. So: prod = empty always; lock ONLY on the
-- full-raw local rebuild machine, after a year is final+synced+golden-verified.
--
-- Re-applying this file is safe: CREATE TABLE IF NOT EXISTS,
-- CREATE OR REPLACE FUNCTION, and DROP TRIGGER IF EXISTS + CREATE TRIGGER.

-- ---------------------------------------------------------------------------
-- 1. The lock registry. A row == "this (school_id, session) is frozen/final."
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS locked_sessions (
    school_id     uuid        NOT NULL REFERENCES schools(school_id),
    session       text        NOT NULL,
    locked_at     timestamptz NOT NULL DEFAULT now(),
    locked_by     text,
    -- md5 checksum of the (school_id, session) fact slice at lock time, so an
    -- operator can later prove the frozen data is byte-identical.
    fact_checksum text,
    reason        text,
    PRIMARY KEY (school_id, session)
);

COMMENT ON TABLE locked_sessions IS
    'Historic-lock registry (MASTER_PLAN §LOCK). A row freezes a '
    '(school_id, session) fact slice; the fact_student_submission delete/'
    'truncate triggers refuse to erase any locked slice. Empty => triggers inert.';

-- ---------------------------------------------------------------------------
-- 2. Row-level guard (BEFORE DELETE ... FOR EACH ROW).
--    Fires once per row a DELETE would remove. Raises only if THAT row belongs
--    to a locked (school_id, session). When locked_sessions is empty the
--    EXISTS is always false => the delete proceeds untouched (inert).
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION fact_locked_session_delete_guard()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM locked_sessions ls
        WHERE ls.school_id = OLD.school_id
          AND ls.session   = OLD.session
    ) THEN
        RAISE EXCEPTION
            'fact_student_submission: session % for school % is LOCKED (historic-lock); DELETE refused',
            OLD.session, OLD.school_id
            USING ERRCODE = 'raise_exception';
    END IF;
    RETURN OLD;  -- allow the delete of this (unlocked) row
END;
$$;

-- ---------------------------------------------------------------------------
-- 3. Statement-level guard (BEFORE TRUNCATE ... FOR EACH STATEMENT).
--    A TRUNCATE removes EVERY row, so it necessarily hits any locked slice.
--    Therefore: refuse the TRUNCATE if ANY lock exists at all. When
--    locked_sessions is empty the EXISTS is false => the TRUNCATE proceeds,
--    which is exactly what the normal full-rebuild relies on.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION fact_locked_session_truncate_guard()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF EXISTS (SELECT 1 FROM locked_sessions) THEN
        RAISE EXCEPTION
            'fact_student_submission: TRUNCATE refused — % locked session(s) exist (historic-lock); a TRUNCATE would erase frozen data',
            (SELECT count(*) FROM locked_sessions)
            USING ERRCODE = 'raise_exception';
    END IF;
    RETURN NULL;  -- statement-level triggers ignore the return value
END;
$$;

-- ---------------------------------------------------------------------------
-- 4. Wire up both triggers (idempotent: drop-then-create).
--    Two triggers are required because DELETE guards are row-level (need OLD)
--    while TRUNCATE guards are statement-level (no OLD, fires once).
-- ---------------------------------------------------------------------------
DROP TRIGGER IF EXISTS trg_fact_locked_session_delete ON fact_student_submission;
CREATE TRIGGER trg_fact_locked_session_delete
    BEFORE DELETE ON fact_student_submission
    FOR EACH ROW
    EXECUTE FUNCTION fact_locked_session_delete_guard();

DROP TRIGGER IF EXISTS trg_fact_locked_session_truncate ON fact_student_submission;
CREATE TRIGGER trg_fact_locked_session_truncate
    BEFORE TRUNCATE ON fact_student_submission
    FOR EACH STATEMENT
    EXECUTE FUNCTION fact_locked_session_truncate_guard();
