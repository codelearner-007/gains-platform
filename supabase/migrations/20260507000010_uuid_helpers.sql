CREATE OR REPLACE FUNCTION uuid_2(c1 text, c2 text)
RETURNS text AS $$
  SELECT encode(digest(concat_ws('_', c1, c2), 'sha256'), 'hex');
$$ LANGUAGE sql IMMUTABLE PARALLEL SAFE;

CREATE OR REPLACE FUNCTION uuid_5(c1 text, c2 text, c3 text, c4 text, c5 text)
RETURNS text AS $$
  SELECT encode(digest(concat_ws('_', c1, c2, c3, c4, c5), 'sha256'), 'hex');
$$ LANGUAGE sql IMMUTABLE PARALLEL SAFE;

CREATE OR REPLACE FUNCTION uuid_6(c1 text, c2 text, c3 text, c4 text, c5 text, c6 text)
RETURNS text AS $$
  SELECT encode(digest(concat_ws('_', c1, c2, c3, c4, c5, c6), 'sha256'), 'hex');
$$ LANGUAGE sql IMMUTABLE PARALLEL SAFE;

-- D1 fix (user decision 2026-05-06): Schoology_py.ipynb line 836-841 defines
-- generate_uuid_7 with a concat_ws("_", ...) immediately overwritten by
-- concat(...) on the next line, dropping the separator. We deliberately keep
-- the separator here for consistency with uuid_2/5/6/8. Hash IDs produced by
-- this function will NOT match legacy PBIX hash IDs that called the buggy
-- helper. This was confirmed safe by the user: no external system references
-- those hashes (they are internal join keys only).
CREATE OR REPLACE FUNCTION uuid_7(c1 text, c2 text, c3 text, c4 text, c5 text, c6 text, c7 text)
RETURNS text AS $$
  SELECT encode(digest(concat_ws('_', c1, c2, c3, c4, c5, c6, c7), 'sha256'), 'hex');
$$ LANGUAGE sql IMMUTABLE PARALLEL SAFE;

CREATE OR REPLACE FUNCTION uuid_8(c1 text, c2 text, c3 text, c4 text, c5 text, c6 text, c7 text, c8 text)
RETURNS text AS $$
  SELECT encode(digest(concat_ws('_', c1, c2, c3, c4, c5, c6, c7, c8), 'sha256'), 'hex');
$$ LANGUAGE sql IMMUTABLE PARALLEL SAFE;

GRANT EXECUTE ON FUNCTION uuid_2(text, text) TO anon, authenticated, service_role;
GRANT EXECUTE ON FUNCTION uuid_5(text, text, text, text, text) TO anon, authenticated, service_role;
GRANT EXECUTE ON FUNCTION uuid_6(text, text, text, text, text, text) TO anon, authenticated, service_role;
GRANT EXECUTE ON FUNCTION uuid_7(text, text, text, text, text, text, text) TO anon, authenticated, service_role;
GRANT EXECUTE ON FUNCTION uuid_8(text, text, text, text, text, text, text, text) TO anon, authenticated, service_role;
