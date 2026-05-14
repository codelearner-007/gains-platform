-- D2 Path A (user decision 2026-05-06): dim_standard / dim_strand are GLOBAL
-- (not per-tenant) lookup tables loaded once from a static seed extracted
-- from the live PBIX file. No live external sync. Data lives in
-- supabase/seeds/dim_standard.csv (7,958 rows) and supabase/seeds/dim_strand.csv
-- (7,071 rows). After `supabase db reset`, run:
--   python supabase/seeds/load_standards.py
-- to bulk-load the rows. We do NOT use psql `\copy` here because Supabase's
-- migration runner does not process psql meta-commands, and inlining 7,958
-- INSERT statements with embedded HTML descriptions makes for a fragile
-- migration file. The Python loader is idempotent (skips load if row counts
-- already match).
--
-- B2 — dim_strand is GLOBAL by notebook design: Schoology_py.ipynb section
-- 8 (cell @ lines 1102-1128 of 40_schoology_py_spec.md) rebuilds dim_strand
-- per ingestion from `dim_question_data` UNIONED across all schools, then
-- publishes it as a single global lookup. There is therefore no school_id
-- discriminator on this table, and no RLS. Phase 2 transformations must
-- TRUNCATE-and-rebuild dim_strand on every ingest run (legacy parity).

-- PK is uniques_id (notebook line 1097 publishes with primary_key='uniquesID').
-- The Identifier column is NOT unique in the seed (7,025 distinct identifiers
-- across 7,958 distinct uniques_id rows because one Identifier can map to
-- multiple Schoology_Standard codes — e.g. MAFS.K.CC.1.1 vs MA.K.MAFS.K.CC.1.1
-- which are FL-state-MAFS aliases of the same Identifier UUID).
CREATE TABLE dim_standard (
  uniques_id                    TEXT PRIMARY KEY,
  identifier                    TEXT NOT NULL,
  schoology_standard            TEXT,
  standard_new                  TEXT,
  strand                        TEXT,
  subject                       TEXT,
  cluster                       TEXT,
  description                   TEXT,
  custom_cleaned_description    TEXT,
  direct_link                   TEXT,
  cpalms_standard               TEXT,
  cognitive_complexity_rating   TEXT,
  language                      TEXT,
  grader                        TEXT,
  last_change_date_time         TIMESTAMPTZ,
  rundate                       DATE
);
CREATE INDEX dim_standard_identifier_idx         ON dim_standard (identifier);
CREATE INDEX dim_standard_schoology_standard_idx ON dim_standard (schoology_standard);
CREATE INDEX dim_standard_strand_idx             ON dim_standard (strand);

-- The legacy notebook's `ID` (Spark monotonically_increasing_id) is NOT unique
-- in the seed CSV (a small handful of fully-duplicated rows survived the
-- legacy dedupe — e.g. ID 2000 appears twice). We preserve every row in the
-- seed by using a surrogate dim_strand_pk; the legacy `id` and `strand_id`
-- (SHA-256 join key, also non-unique) are kept as ordinary indexed columns.
CREATE TABLE dim_strand (
  dim_strand_pk  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  id             BIGINT,
  identifier     TEXT,
  strand         TEXT,
  strand_id      TEXT
);
CREATE INDEX dim_strand_id_idx         ON dim_strand (id);
CREATE INDEX dim_strand_identifier_idx ON dim_strand (identifier);
CREATE INDEX dim_strand_strand_id_idx  ON dim_strand (strand_id);

GRANT SELECT ON dim_standard TO anon, authenticated;
GRANT SELECT ON dim_strand   TO anon, authenticated;

DO $$ BEGIN
  RAISE NOTICE 'dim_standard/dim_strand created. Run `python supabase/seeds/load_standards.py` to load 7958 + 7071 rows.';
END $$;
