-- Staging: dim_standard pass-through (no-op).
--
-- D2 Path A (user decision 2026-05-06): dim_standard is a GLOBAL static seed
-- loaded once via supabase/seeds/load_standards.py (7,958 rows). It is NOT
-- rebuilt per ingestion. This file exists only to keep the staging phase
-- symmetrical with the notebook layout — downstream models (dim_question_data,
-- dim_strand) read directly from the seeded dim_standard table.
--
-- See `tasks/backlog/01-gains-pipeline-finalized-plan.md` §2 D2 and
-- `data/_pbix_extract/40_schoology_py_spec.md` section 6.

SELECT 1;  -- intentional no-op (see header comment)
