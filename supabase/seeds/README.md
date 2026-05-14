# supabase/seeds — Phase 0 seed data

This folder contains seed data that is loaded **after** `supabase db reset`
applies all migrations under `supabase/migrations/`. The migrations create the
schema; seeds populate it.

## Files

| File | Purpose | Loaded by |
|------|---------|-----------|
| `dim_standard.csv` | 7,958 rows — global standards lookup (PBIX extract). | `load_standards.py` |
| `dim_strand.csv` | 7,071 rows — global strand lookup (PBIX extract). | `load_standards.py` |
| `load_standards.py` | Idempotent bulk loader for the two CSVs. | Run manually after `db reset`. |
| `rbac_seed.sql` | Roles + permissions (auto-loaded by `db reset`). | `supabase db reset` (via `seed.sql` if linked). |
| `schools_athenian.sql` | First-tenant `schools` row + IDs. | Manual `psql -f` after `db reset`. |
| `teacher_pair_overrides.sql` | First-tenant teacher-pair config. | Manual `psql -f` after `db reset`. |

## Two-step workflow

```
cd supabase
npx supabase db reset                       # 1) apply migrations + seed.sql
python supabase/seeds/load_standards.py     # 2) bulk-load standards CSVs
```

After both steps, validation gates 1–9 (see Phase 0 plan) should pass.

## Why `load_standards.py` runs separately

1. **CSV size.** `dim_standard.csv` has 7,958 rows with embedded HTML
   descriptions (multi-paragraph CPALMS markup). Inlining 7,958 `INSERT`
   statements into a migration file is fragile (escaping, file size, slow
   migrate cycle, hard to diff).
2. **`\copy` is not portable.** `psql`'s `\copy` meta-command is the natural
   fast path for bulk CSV ingest, but Supabase's migration runner does not
   process psql meta-commands — it sends each migration to the server as plain
   SQL. Server-side `COPY ... FROM '/path/to/file'` requires the file to be
   present on the database server and the connecting role to have superuser
   privileges, neither of which holds for the Supabase-managed Postgres.
3. **Idempotency.** The Python loader checks current row counts against the
   CSVs and skips reload when they already match (override with `--force`).
   This is wanted for repeat `db reset` cycles in dev, and is awkward to
   express inside a migration.

## Idempotency contract

`load_standards.py`:
- Skips load if `count(*)` already matches the CSV row count for both tables.
- With `--force`, truncates and reloads both tables.
- Reads `$DATABASE_URL` (default `postgresql://postgres:postgres@127.0.0.1:56322/postgres`).

## After-reset checklist

```
psql "$DATABASE_URL" -c "SELECT count(*) FROM dim_standard;"   -- expect 7958
psql "$DATABASE_URL" -c "SELECT count(*) FROM dim_strand;"     -- expect 7071
psql "$DATABASE_URL" -c "SELECT count(*) FROM schools;"        -- expect ≥1 (Athenian seed)
psql "$DATABASE_URL" -c "SELECT count(*) FROM teacher_pair_overrides;"  -- expect >0
```
