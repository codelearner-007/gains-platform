# Standards Alignment — Sourcing & Caveats

This document explains where the platform gets per-question standards
alignment data, what happens when it's missing, and how to fix the
gaps at the source.

## Where alignment data comes from

| Layer | Source | What it provides |
|---|---|---|
| **Taxonomy** (`dim_standard`) | Static seed at `supabase/seeds/dim_standard.csv` (7,958 rows) loaded by `supabase/seeds/load_standards.py`. Originally extracted from the EdvanceLearning CASE Network LMS API. | The catalogue of standards: `identifier`, `schoology_standard`, `cpalms_standard`, `strand`, `description`, `subject`. |
| **Alignment** (`dim_question_data.standard` → `dim_question_data.identifier`) | The `Standards{N}` columns inside the Schoology Test/Quiz **"Export Stats"** CSV (one column per learning objective aligned to the question). Downloaded by the scraper (`gains/scraper/schoology-exporter.js`), parsed by `backend/app/jobs/parsers/question_data.py`. | Which question is aligned to which standard. |

`dim_strand` is **derived** from the two: it joins `dim_question_data.standard` to `dim_standard.schoology_standard` via substring match (notebook line 989 of the legacy Schoology PySpark pipeline) and keeps the distinct `(identifier, strand)` pairs.

## When the alignment is missing

The Schoology UI's "Export Stats → export_content[export_question_data]" CSV only includes `Standards{N}` columns **when at least one question on the assessment has an aligned learning objective**. If teachers authored a Test/Quiz in Schoology and never used the "Align Learning Objective" control, the export ships with no `Standards*` columns at all. The pipeline correctly absorbs this (`backend/tests/jobs/test_parsers_question_data.py::TestNoStandardsFile` pins this case), but downstream:

- `dim_question_data.standard` is `NULL` for every row.
- `dim_question_data.identifier` is `NULL` (the substring join to `dim_standard` has nothing to match).
- `dim_strand` gets zero rows for the affected items.
- `fact_student_submission.identifier` / `.strand_id` are `NULL`.
- `cube_standard_summary` only emits the school/item-level subtotal rows, with `NULL` identifier/strand_id.
- **Standards Deep Dive, Strand Summary, Standard Summary** render empty because every join falls through.

## How the platform surfaces the gap

Each affected report payload now includes a `data_quality: AlignmentDataQuality | null` block:

```json
{
  "alignment_status": "missing",
  "questions_total": 10,
  "questions_with_alignment": 0,
  "items_total": 1,
  "items_with_alignment": 0,
  "remediation_hint": "Open this assessment in Schoology, edit each question, and use \"Align Learning Objective\" to attach the relevant standards. Re-ingest after the next Export Stats download."
}
```

When `alignment_status === "missing"` the page renders `AlignmentEmptyState` instead of empty charts; KPIs that don't depend on alignment (total students, total questions, grade average from school summary) still render. `alignment_status` is one of `full`, `partial`, `missing`.

For tenant-wide auditing, admins can hit `GET /api/v1/reports/data-quality/standards-alignment`. It returns `AlignmentDataQualityReport` — one row per assessment with `pct_aligned`, `questions_with_alignment`, and `alignment_status`, plus tenant totals.

## How to fix at the source

1. **Schoology UI fix (preferred).** Open the assessment in Schoology, edit each question, click **Align Learning Objective**, and attach one or more standards from the District Learning Objectives Library. Save. Re-run the Export Stats download (next scheduled scraper run). The `Standards{N}` columns will appear and the next pipeline run will populate `dim_question_data.identifier`.
2. **Install the standards library first if needed.** PowerSchool's recommended setup is "Standards Grade Passback from PowerSchool SIS → Schoology District Learning Objectives Library" (one-time tenant admin task) so teachers have a populated library to align against.
3. **Migrate Quiz → Assessment (AMP)?** PowerSchool's *Convert a test or quiz to course assessments* tool preserves alignments. If the school is moving to AMP anyway, this is the natural path — but the AMP export uses a different column shape (`learning_objectives` from the Item Analysis Report, not `Standards{N}`), so the parser would need a sibling code path. Not currently implemented.

## Alias safety — never drop the Schoology course-prefix rows on refresh

The per-question rollups (Standards Deep Dive, Standard/Strand Summary, QRA
strand tables) join the *raw* label an assessment emitted
(`dim_question_data.standard`) to `dim_standard.schoology_standard` via an
**exact** match. Schoology emits up to four parallel `Standards` columns per
question — including course-prefix aliases like `AI.MA.912.AR.3.1` next to the
canonical `MA.912.AR.3.1`, and embedded `*.MAFS.*` forms (see
`docs/audit/legacy-schoology-cpalms-mapping.md`). Those alias rows exist in
`supabase/seeds/dim_standard.csv` (1,340 of them) **only** because legacy's
Spark pipeline observed them in the gradebook CSVs and unioned them in. The
CPALMS / 1EdTech CASE feed emits one canonical row per leaf and does **not**
contain them.

Consequence: a `refresh_standards.py --full-pull` run regenerates the seed
purely from CPALMS and would **silently drop every alias row**. The exact-match
join then falls through for any question aligned to an alias form, dumping it
into the synthetic `Other` bucket and quietly corrupting the rollups — with no
error anywhere.

Two safety nets enforce the invariant:

1. **Refresh guard.** `refresh_standards.py` defaults to the safe
   *update-in-place* mode (preserves `Schoology_Standard` and its derived
   columns, keyed on `Identifier`). The destructive `--full-pull` path now
   counts the alias rows it would drop and **aborts** unless the operator
   passes `--i-understand-this-drops-aliases`. If you ever take that path, you
   must re-augment aliases from the Question-Data CSVs afterward (the
   "IMS-canonical plus observed-alias" pattern documented in
   `docs/audit/legacy-schoology-cpalms-mapping.md` §8).
2. **Coverage test.** `backend/tests/api/test_standards_alias_coverage.py`
   runs against the live seeded DB and fails if any *code-shaped*
   `dim_question_data.standard` lacks an exact `dim_standard.schoology_standard`
   match — i.e. it detects dropped aliases. It tolerates non-code junk labels
   (e.g. a literal `"Social Studies"` typed into a Standards column) which are
   surfaced separately via the `labels_not_mapped` data-quality cause. Run it
   after every standards refresh:
   `cd backend && ./venv/bin/python -m pytest tests/api/test_standards_alias_coverage.py`.

## What we can NOT do

- **There is no Schoology REST API for per-question alignments** on the legacy Test/Quiz tool. The closest endpoint (`with_tags=1`) returns assignment-level tags, not per-question. Confirmed against `developers.schoology.com/api-documentation/rest-api-v1/` (May 2026).
- **NLP-inferring standards from question text** would fabricate analytics signal — explicitly out of scope.

## References

- Root-cause investigation: [`tasks/cleanup/standards-missing-rca-2026-05-15.md`](../tasks/cleanup/standards-missing-rca-2026-05-15.md)
- Legacy pipeline spec: `data/_pbix_extract/40_schoology_py_spec.md` §3, §4.5, §4.6
- Schoology export bot history: `gains/SCHOOLOGY_BOT_RESEARCH_AND_HISTORY.md`
- Parser code: `backend/app/jobs/parsers/question_data.py`
- Substring-join transformation: `backend/app/transformations/04_dimensions_c/dim_question_data.sql`
- Strand build: `backend/app/transformations/05_dimensions_d/dim_strand.sql`
- DQ endpoint: `backend/app/api/v1/reports.py::standards_alignment_data_quality`
