# supabase/seeds — GAINS data toolchain

This folder holds the seed data and the production-reusable data toolchain.
Seeds run **after** `supabase db reset` applies the migrations under
`supabase/migrations/`. The migrations create the schema; seeds + the toolchain
populate it.

The toolchain is **three tiers**: Tier 1 auto-runs on `db reset`; Tiers 2-3 are
explicit, idempotent, and reusable in production.

---

## Tier 1 — schema + base seed (auto via `supabase db reset`)

Loaded automatically because they are listed in `supabase/config.toml`
`[db.seed].sql_paths`:

| File | Purpose |
|------|---------|
| `rbac_seed.sql` | 13 permissions + grant of all permissions to `super_admin`. (System roles `super_admin` / `user` are created by the `rbac_system` migration so they exist on every deploy.) |
| `schools_all.sql` | All active `schools` rows (Athenian + 4) with `schoology_building_id`, `schoology_school_id`, per-school `student_role_id`, and the regex/window/session config. Idempotent (`ON CONFLICT (schoology_building_id) DO UPDATE`). Dev/bootstrap fixture — in production, schools are onboarded via the tenancy control plane, not this file. |
| `teacher_pair_overrides.sql` | Teacher-pair config (resolves once all school rows exist). |

`schools_athenian.sql` is the **superseded** single-tenant seed kept for
reference; `schools_all.sql` replaced it in `config.toml`.

## Tier 2 — global standards (manual, idempotent)

| File | Purpose |
|------|---------|
| `dim_standard.csv` | 7,958 rows — global standards lookup. |
| `dim_strand.csv` | 7,071 rows — global strand lookup. |
| `load_standards.py` | Idempotent bulk loader for the two CSVs (skips if row counts match; `--force` to reload). Reads `$DATABASE_URL`. |
| `refresh_standards.py` | Regenerator for `dim_standard` (CPALMS / CASE Network). |

Standards are kept out of the auto-seed because the CSVs are large (embedded
HTML descriptions) and `psql \copy` is not portable to the Supabase migration
runner. The loader is invoked for you by `gains_data seed` (below); run it
directly only when reloading standards in isolation.

## Tier 3 — tenant data: the `gains_data` CLI

One source-agnostic CLI wraps the proven ingest + transformation pipeline
(`backend/app/jobs/ingest_schoology.py` + `backend/app/transformations/`).
It never duplicates ingest logic.

```
cd backend
python -m app.jobs.gains_data wipe    [--keep-standards] [--yes]
python -m app.jobs.gains_data seed    [--superadmin-email …] [--superadmin-password …]
python -m app.jobs.gains_data ingest  [--school SHORT|ALL] [--data-root PATH]
                                      [--source local|azure]
                                      [--limit-per-school N] [--seed S]
python -m app.jobs.gains_data rebuild [--limit-per-school N] [--seed S] [--yes]
```

- **`wipe`** — `pg_dump` backup to `/tmp/gains-backup/` FIRST, then FK-safe
  `TRUNCATE` of every `raw_*` / `stg_*` / `dim_*` / `fact_*` / `cube_*` table
  plus `ingested_files` / `ingestion_runs`, then deletes all non-superadmin
  `auth.users`. `--keep-standards` (the default) preserves
  `dim_standard` / `dim_strand`. **Refuses without `--yes`.** Keeps schema,
  migrations, RBAC, and the superadmin.
- **`seed`** — idempotent base bootstrap: ensures `schools_all` + standards
  (calls `load_standards`) + RBAC grants are present and creates exactly ONE
  superadmin (default `m.arham@insightanalytics.net` / `!Password123`),
  GoTrue-safe (token columns `''`, `email_confirmed_at` set) with the
  `super_admin` role assigned by name lookup.
- **`ingest`** — source-agnostic via `make_blob_client`. `--school ALL`
  iterates active schools; the staging join resolves each row's school from the
  CSV `User School ID`, so a single mixed `--data-root` ingests every school
  correctly. `--limit-per-school N` **deterministically samples N assessments
  per school** (an assessment = a distinct `(school, Item_ID)` recovered from
  CSV rows), seeded by `--seed`; it never splits a
  `Question-Data` / `Submission-Summary` / `Student-Submissions` trio. Omitting
  `--limit-per-school` = FULL ingest (the production default).
- **`rebuild`** — the one-command path: `wipe --keep-standards` → `seed` →
  `ingest --school ALL [--limit-per-school N]`.

### Typical flows

Clean dev rebuild with a 100-assessment-per-school sample:

```
cd backend
python -m app.jobs.gains_data rebuild --limit-per-school 100 --seed 42 --yes \
    --data-root /path/to/backup/synapse/pre_landing/Schoology
```

From-scratch local bootstrap:

```
cd supabase && npx supabase db reset          # Tier 1 (rbac + schools + overrides)
cd ../backend
python -m app.jobs.gains_data seed             # Tier 2 standards + ONE superadmin
python -m app.jobs.gains_data ingest --school ALL \
    --data-root /path/to/backup/synapse/pre_landing/Schoology   # Tier 3 FULL ingest
```

Production later swaps `--source local --data-root …` for `--source azure`
(the Phase-7 Azure blob client) behind the same CLI — no other change.

---

## LTI

`seed_lti.py seed` registers the Schoology 1.3 platform template (placeholder
`client_id`, filled in by the org admin after install). `seed_lti.py launch`
runs a transient mock LTI launch end-to-end for dev/test (registers + tears
down its own mock platform; depends on no demo data).

## `_archive/`

`_archive/load_real_schools.py` is the retired Method-B parquet loader
(cubes-only, pseudonymized, per-student-empty). Method-A (`gains_data ingest`)
replaced it; it is kept one release as a rollback path.

---

## Tests

```
cd backend && ./venv/bin/python -m pytest tests/jobs/test_gains_data.py -q
```

The DB-mutating additivity test is gated behind `GAINS_TEST_DATABASE_URL`
(point it at a throwaway DB) so it never touches the live, audit-verified DB.
The sampling / trio-integrity / wipe-refusal / keep-standards tests run against
the live schema read-only and are always collected.
