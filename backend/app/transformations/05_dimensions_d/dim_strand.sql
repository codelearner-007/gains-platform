-- dim_strand — rebuilt on every run from dim_question_data ⨝ dim_standard.
-- Notebook lines 1102-1128 (40_schoology_py_spec.md §4.6):
--   question_data = oea.load(... dim_question_data).drop("Identifier")
--   standard      = oea.load(... dim_standard)
--   df_dim_question_data = standard.join(
--       question_data,
--       standard.Schoology_Standard.contains(question_data.Standard),
--       how="left")
--   dim_strand = df_dim_question_data[["Identifier","Strand"]]
--                  .dropDuplicates(["Identifier","Strand"])
--   dim_strand = dim_strand.withColumn("ID", monotonically_increasing_id())
--   dim_strand = dim_strand.withColumn(
--       "strand_ID", generate_uuid_2(dim_strand['Identifier'], dim_strand['Strand']))
--   schoology.publish(dim_strand, ..., primary_key='ID')
--
-- Our schema deviates from the notebook: dim_strand_pk is a Postgres
-- IDENTITY-generated synthetic PK (see migration 045). The notebook's `id`
-- column is preserved as a non-PK BIGINT — we recompute it via ROW_NUMBER
-- OVER (ORDER BY identifier, strand) for stable ordering. After TRUNCATE +
-- INSERT the dim_strand_pk IDENTITY restarts (see ALTER SEQUENCE below).

TRUNCATE TABLE dim_strand RESTART IDENTITY;

INSERT INTO dim_strand (id, identifier, strand, strand_id)
WITH joined AS (
  -- Exact-identifier join — the notebook joins via reverse substring
  -- (`Schoology_Standard.contains(Standard)`), which has the same
  -- prefix-collision class of bug as dim_question_data.standard's forward
  -- substring (see `.hermes/report-parity/pipeline-audit-2026-05-18.md §B3`).
  -- After §B1's word-boundary fix in `dim_question_data.sql`,
  -- `dim_question_data.identifier` is stamped correctly per question. We can
  -- therefore project (identifier, strand) directly from
  -- `dim_question_data ⨝ dim_standard` ON identifier, which avoids the
  -- substring asymmetry entirely (some long-form identifiers had no row in
  -- dim_strand because the reverse substring failed — fact rows survived but
  -- with `strand_id IS NULL`).
  SELECT DISTINCT
    ds.identifier,
    ds.strand
  FROM dim_question_data dqd
  JOIN dim_standard ds
    ON ds.identifier = dqd.identifier
  WHERE ds.identifier IS NOT NULL
    AND ds.strand     IS NOT NULL
    AND ds.strand     <> ''
)
SELECT
  ROW_NUMBER() OVER (ORDER BY identifier, strand) AS id,
  identifier,
  strand,
  uuid_2(identifier, strand) AS strand_id
FROM joined;
