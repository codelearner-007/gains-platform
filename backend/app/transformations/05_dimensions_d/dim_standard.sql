-- D2 Path A (user decision 2026-05-06): dim_standard is loaded ONCE from
-- supabase/seeds/dim_standard.csv (7,958 rows) via
-- supabase/seeds/load_standards.py — run after `supabase db reset`.
-- It is NEVER rebuilt by the transformation pipeline.
--
-- See `tasks/backlog/01-gains-pipeline-finalized-plan.md` §2 D2 and
-- supabase/migrations/20260507000045_standards_seed.sql.

SELECT 1;  -- intentional no-op (see header comment)
