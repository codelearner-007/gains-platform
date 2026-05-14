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
  -- Notebook: standard.Schoology_Standard.contains(question_data.Standard)
  -- ILIKE preserves case-insensitivity (notebook is on Spark, which is also
  -- case-sensitive — but we follow the substring-join convention used
  -- elsewhere in the pipeline for consistency with dim_question_data above).
  SELECT DISTINCT
    ds.identifier,
    ds.strand
  FROM dim_question_data dqd
  JOIN dim_standard ds
    ON dqd.standard IS NOT NULL
   AND ds.schoology_standard ILIKE '%' || dqd.standard || '%'
  WHERE ds.identifier IS NOT NULL
    AND ds.strand     IS NOT NULL
)
SELECT
  ROW_NUMBER() OVER (ORDER BY identifier, strand) AS id,
  identifier,
  strand,
  uuid_2(identifier, strand) AS strand_id
FROM joined;
