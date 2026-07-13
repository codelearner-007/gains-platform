-- =============================================================================
-- dim_standard collision + junk cleanup (2026-07 audit, F-E1 / F-E5).
--
-- RUN AFTER load_standards.py (dim_standard is a static seed loaded from
-- dim_standard.csv; the pipeline never rebuilds it). Idempotent.
--
-- WHY: the legacy notebook minted alias rows by substring/ILIKE matching, so a
-- short benchmark code (…W.3.1) got attached as an extra row to every longer
-- code it is a substring of (…W.3.10 … .16). The fact identifier join pins the
-- lexically-smallest identifier, which is often the POLLUTED (wrong-benchmark)
-- one -> wrong standard description + mis-bucketed per-standard averages on
-- 25,858 fact rows across 35 assessments.
--
-- FIX (provably safe):
--   (1) SUBSTRING pollution: for a colliding schoology_standard whose EXACTLY
--       ONE identifier's standard_new equals the code's own trailing segment,
--       that identifier is the correct benchmark; delete the other (polluted)
--       alias row(s). Codes where NO identifier matches the trailing segment are
--       genuine PARENT/cluster codes (children legitimately differ) and are left
--       untouched. 28 rows deleted.
--   (2) JUNK numeric codes ('0.1','0.11', …): truncated fragments captured as
--       schoology_standard for unrelated benchmarks. 0 fact rows reference them,
--       and every one of their identifiers also exists on a real code row, so
--       deleting the junk rows cannot orphan any fact.identifier. 27 rows deleted.
--
-- After running this, re-derive fact_student_submission.identifier (facts
-- rebuild or scoped UPDATE) and rebuild the standards cubes.
-- =============================================================================

-- (1) delete polluted substring aliases
WITH coll AS (
  SELECT schoology_standard,
         split_part(schoology_standard, '.', array_length(string_to_array(schoology_standard, '.'), 1)) AS last_seg
  FROM dim_standard
  WHERE schoology_standard IS NOT NULL AND btrim(schoology_standard) <> ''
  GROUP BY 1 HAVING count(DISTINCT identifier) > 1
),
fixable AS (
  SELECT c.schoology_standard, c.last_seg
  FROM coll c JOIN dim_standard ds USING (schoology_standard)
  GROUP BY 1, 2
  HAVING count(*) FILTER (WHERE ds.standard_new = c.last_seg) = 1        -- exactly one true benchmark
     AND bool_or(c.schoology_standard ~ '^[0-9]+') = false                -- not a junk numeric code
)
DELETE FROM dim_standard ds USING fixable f
WHERE ds.schoology_standard = f.schoology_standard
  AND ds.standard_new IS DISTINCT FROM f.last_seg;

-- (2) delete junk numeric-only codes (identifiers survive on real rows)
DELETE FROM dim_standard
WHERE schoology_standard ~ '^[0-9]+(\.[0-9]+)?$';
