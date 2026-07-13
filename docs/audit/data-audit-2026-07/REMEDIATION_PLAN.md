# GAINS Data-Integrity Audit & Remediation Plan

**Date:** 2026-07-11  ·  **Scope:** local Supabase (`127.0.0.1:56322`), 3 schools (Athenian, CFP, Crestwell), ~1.65M fact rows  ·  **Status:** audit complete, **no fixes applied** — this is the plan.

**How this was produced.** A 34-agent detection sweep (18 pattern detectors across every layer of the star schema + a full-inventory human-style reasoning pass over all 3,700 assessments) produced 194 raw findings. These were de-duplicated into 50 distinct groups, then each group was **independently reproduced from scratch** and the critical/high ones were **adversarially refuted** (a dedicated agent hunted for the benign explanation) on Opus 4.8. A completeness critic then proposed follow-up probes. Result: **45 confirmed, 4 refuted as benign-by-design, 1 not-reproduced, 20 probe findings.** Machine-readable detail in `audit_findings.json`; per-finding evidence in `evidence/`.

**Trust note.** Every finding here survived independent re-derivation. Counts may differ slightly from a detector's first pass because the reproduce/refute agents recomputed them. Where a finding was *downgraded or overturned*, it is in §7 (Ruled Out), not in the fix list — do not spend effort there.

---

## 1. Executive Summary

The headline your teachers experience — *"I open a report and see wrong, missing, or duplicated data"* — is real and traces to a **small number of root mechanisms**, not 45 unrelated bugs. The good news: the earlier misfiling relabel **landed correctly at the dimension layer** — subject-vs-standards is 100% clean across all 3,213 assessments that carry usable standards, and fact-level subject labels are perfectly consistent with their standards. The corruption that remains falls into six buckets:

| # | Root mechanism | What teachers see | Findings | Where the fix lives |
|---|---|---|---|---|
| **M1** | **Read-layer retake bug**: 3 report queries pick an *arbitrary* attempt, not the latest | Retake students' scores are understated; the per-student report contradicts the assessment report; numbers change between refreshes | F-A1, F-A2 | **Code** (self-healing) |
| **M2** | **Zero-poisoning + broken join** in Standard/Strand rollups | Standards students scored 75–94% on render as 7–20% and get flagged "Needs Attention" | F-A3 | **Code** (fix exists unmerged) |
| **M3** | **Source misfiling** (Schoology folder/section mis-assignment) faithfully mirrored | Assessment appears under the wrong subject/grade; real class report is missing it | F-D1 | **Data** (durable overrides) |
| **M4** | **Twin/split fragmentation**: one assessment minted under 2+ `subject_id`s / label variants | Same test listed twice, each with half the class; per-question stats on partial cohorts; double-counted students | F-D2, F-C1, F-C2 | **Data + pipeline** |
| **M5** | **Stale derived layer**: in-place fixes updated rows without rebuilding cubes/`dim_question_data` | Report header shows pre-fix numbers (1 student instead of 19); wrong "correct answer"; values flip between requests | F-C3, F-D8, F-E* | **Rebuild + data** |
| **M6** | **Standards seed defects**: ILIKE alias collisions, missing/blank descriptions, junk codes | Wrong standard descriptions, pooled/doubled per-standard averages, blank description cells | F-E1…E6 | **Seed + rebuild** |
| **—** | **Security (out-of-band):** one cube has RLS disabled; backup tables expose student PII to `anon` | Cross-tenant data leak risk | F-B1, F-B2 | **Migration/grants** |

**Two structural truths that shape the whole plan:**

1. **Durable vs in-place.** The source-misfiling and twin defects were previously patched with **in-place `UPDATE`s on derived tables**. Any full pipeline re-run *regresses* them, and because **production has no raw/staging layer**, prod fixes can never be re-derived — they must be replayed by hand. The durable fix vehicle is the **seed-based override mechanism** (`subject_grade_overrides.sql` and siblings), which survives rebuilds. **Every source-data fix in this plan should be expressed as an override seed, not an ad-hoc UPDATE.**

2. **Code fixes are free wins.** M1 and M2 are pure read-layer bugs. They need no data migration, self-heal on deploy, and fix the most visible wrong-number complaints. **Ship these first.**

---

## 2. Root-Cause Taxonomy (the six mechanisms in detail)

**M1 — Retake attempt non-determinism (read layer).** The fact table intentionally keeps *every* Schoology attempt. `student_repository.py` correctly collapses to the latest attempt with `ORDER BY … submission DESC NULLS LAST`. But three CTEs in `cube_repository.py` (`fact_dedup` at **L208, L522, L2303**) order by `identifier`/`standard NULLS LAST` **with no `submission DESC`** — verified directly. So for a retaken question they keep whichever attempt sorts first by identifier, i.e. random. **308 assessments** across all 3 schools show a KPI Grade Average computed from mixed attempts; systematic *understatement* (2,136 of 2,907 retake cells shown lower than the true latest); worst single case 16 pp. This is why the per-student report and the assessment report disagree for the same student.

**M2 — Zero-poisoning in Standard/Strand Summary.** The school-wide Standard/Strand pages join `cube_question_summary → cube_question_summary_overall` on `ukey` (a hash of question+correct_answer text). `ukey` has multiple values per logical question when text varies across rows, so the join **silently misses 9–15% of questions**, and the read layer coerces the miss with `AVG(COALESCE(grade_average, 0))` — turning a *linkage gap* into a fake **0%**. Result: hundreds of standards/strands understated (75–94% → 7–20%), mis-bucketed into "Needs Attention," deflated at-target KPI.

**M3 — Source misfiling.** Schoology exports carry subject/grade from the *export folder*, which was sometimes set inconsistently vs the course/section the assessment was actually given in. Our pipeline mirrors it faithfully. **12 assessments** are confirmed misfiled by triangulating three independent signals (section peers + mapped standards + taker home-grade): a Grade-1 science "Genius Challenge" filed as Algebra/Grade 8, a Grade-6 ELA unit test filed Grade 8, CFP Pre-Algebra "Topic 1" filed Math/Grade 7 while Topics 2–7 are Algebra/Grade 8, etc. **This is not a transformation bug** — but it is still teacher-visible and must be corrected via override.

**M4 — Twin/split fragmentation.** `subject_id = hash(school, subject, assessment_type, grade, session, item_name)`. Any variation in *any* of those six inputs across re-exports mints a **new** `subject_id`, so one real assessment becomes two report cards. The `latest_export` dedupe in `fact_student_submission.sql` does run (it operates on staging at build time — see §7 correction), but its `PARTITION BY` **omits** subject/grade/session/assessment_type, so it only dedupes *within* a label combo and never collapses cross-label twins. Compounded by `dim_item`'s one-`subject_id`-per-item rule picking the **first-occurrence** bucket while fact settles on the **latest-export** bucket → 37 items diverge, 29 `subject_id` buckets (7,730 fact rows) are orphaned with **no `dim_item` row** → invisible in the dashboard grid.

**M5 — Stale derived layer.** The misfiling relabel/twin-merge/heal fixes were applied in place: they `UPDATE`d `subject_id` on cube rows but never recomputed the sha256 rollup ids, never re-aggregated `GROUPING SETS` rows, and only partially touched `dim_question_data`. 152 cube rows carry pre-fix labels/keys; report headers show stale counts; `LIMIT 1` over duplicate rollup rows makes the displayed value flip between requests. Separately, `dim_question_data` retains multiple label/answer-key vintages, so cube builds pick the display "correct answer" vintage-blind → 594 question grains where the shown correct answer ≠ what students were graded against.

**M6 — Standards seed defects.** The legacy notebook built `dim_standard` alias rows via substring/ILIKE matching, so short codes (`…W.3.1`) substring-matched longer ones (`…W.3.10–.16`) and stole their identifier+description → **44 codes with duplicate identifiers, 18,220 fact rows pinned to the wrong benchmark.** Plus 264 real codes with no `dim_standard` row (NULL identifier → invisible in standards reports), 279 rows with NULL description (retired MAFS/LAFS), HTML entities in strand labels, and 27 junk numeric-only codes.

---

## 3. Strategy & Sequencing

**Guiding principles**
- **Fix at the right layer.** Read bug → code. Source corruption → durable override seed (never bare UPDATE). Seed defect → seed + regenerate. Stale derived → rebuild.
- **Backup before every data mutation** (`*_bak` snapshot per the runbook pattern) and wrap in a transaction.
- **Rebuild cubes after any fact/dim change**, then validate against KPI baselines (`project_kpi_baseline`) — Athenian is the digit-for-digit legacy anchor and must not move except where a fix intends it to.
- **Local first, prod by replay.** Prod has no pipeline; use the scoped-sync + cubes-only rebuild path in `docs/audit/fixes/02_assessment_misfiling_prod_runbook.md`.
- **RLS-aware validation.** Direct `psql`/service_role queries bypass RLS. Validate teacher-visible results through the tenant-role backend (Playwright/API), per `feedback_rls_bypass_testing`.

**Recommended order (each phase gated by verification before the next):**

```
Phase 0  Security         F-B1, F-B2                     (independent, urgent, no data change)
Phase 1  Read-layer code  F-A1..A6                       (self-healing, biggest visible win, no migration)
Phase 2  Standards seed   F-E1..E6  → rebuild fact+cubes (foundation for correct standards reports)
Phase 3  Pipeline struct  F-C1..C6  → rebuild            (makes rebuilds safe & deterministic)
Phase 4  Data corrections F-D1..D8  (override seeds)     → rebuild cubes
Phase 5  Hygiene          F-F1..F7                       → rebuild affected cubes
Phase 6  Guardrails       F-G* regression tests
Phase 7  Prod replay      per runbook, scoped-sync + cubes-only
```

Phases 1 and 0 can ship immediately and in parallel with everything else — they touch only code/grants. Phases 2–5 are data/rebuild work that must be serialized on local, verified, then replayed to prod.

---

## 4. The Fix Plan — by workstream

Severity: **C**ritical (wrong numbers/data in reports) · **H**igh (wrong/missing labels or data) · **M**edium (latent/hygiene) · **L**ow (cosmetic). Class: **CODE** (read-layer) · **SRC** (source corruption, mirror faithfully → override) · **PIPE** (our transformation logic) · **SEED** (standards seed) · **HYG** (labels).

### Workstream A — Read-layer code fixes *(no data change; deploy-and-done)*

**F-A1 · C · CODE · Retake attempts picked non-deterministically.** Add `f.submission DESC NULLS LAST` as the **first** tiebreak in the `ORDER BY` of the three `fact_dedup` CTEs at `cube_repository.py:208`, `:522`, `:2303` (before `identifier`/`standard`). Mirrors `student_repository.py:104`. Fixes QRA/SDD KPI strip, per-question grade table, and YTD matrix. *Verified: 308 assessments affected; CFP "Module 4 Assessment: Better Together" 65.77% → 71.50% correct.* Add a 2-attempt regression fixture.

**F-A2 · C · CODE · Same bug, per-question grade rows.** Same fix as F-A1 (the L522 CTE feeds the per-question rows and the paginated QRA/SDD tables). Grouped with F-A1 — one change set, one test.

**F-A3 · C · CODE · Standard/Strand grade averages zero-poisoned.** Replace the `ukey` bridge with the standard-code bridge already used per-assessment: `AVG(cqso.grade_average)` grouped by `cqso.standards`/`identifier`, scoped by the filtered `subject_id`s; and **drop the `COALESCE(...,0)`** so an unmatched code is excluded (NULL/BLANK), not counted as 0%. **This exact fix already exists, unmerged, on branch `worktree-temporal-orbiting-sketch` (commits d4c099c, 221bb10).** Action: review and merge that branch (it also rewrites YTD — see F-A4), don't re-implement. *Verified: 813 standard/strand rows deflated.*

**F-A4 · C · CODE · `subject_course_overrides` never reach `dim_question_data`.** `get_ytd_longitudinal_cells`, `get_ytd_longitudinal_standard_units` (`cube_repository.py:2294-2297, 2441-2453`) and `get_school_alignment_quality` (`:1947-1951`) filter `dim_question_data.subject`/`grade` **directly**, but `dqd` structurally can't carry the CFP HS course-name / Crestwell "Reading" override labels — so the slicer value never matches and **14 CFP HS courses lose their entire standards dimension** in YTD Longitudinal (single "Other" column). Fix: scope `dqd` through `dim_item.subject_id → dim_subject` (same pattern as `_QS_SCHOOL_FILTER_SQL`, `cube_repository.py:19-31`). Note the `worktree-temporal-orbiting-sketch` branch rewrites YTD as a `cube_user_summary` pivot — confirm whether that already resolves this before duplicating work.

**F-A5 · H · CODE · Admin alignment-quality list mislabels & mis-scopes.** `list_alignment_quality_by_item` (`cube_repository.py:1981-2030`) uses `MAX(dqd.subject)/MAX(dqd.grade)` — mispicks the conflicting vintage on 15 items and shows the *base* subject (not the override) for 77 CFP + 3 Athenian items; and its coverage denominator silently drops `dqd`-missing questions (33 q + 3 items), inflating apparent alignment. Fix: source subject/grade from `dim_subject` via `dim_item.subject_id`, and derive the question universe from `cube_question_summary`/fact `LEFT JOIN dqd` so missing questions count as unaligned rather than vanish.

**F-A6 · L · CODE · `browse_students` cross-tenant latent join.** `browse_students` joins `dim_student` on `uid` without `school_id` — safe today only because RLS scopes it. Add `AND dst.school_id = <fact-side/GUC school_id>` so correctness doesn't depend solely on RLS. No user impact today; hardening for multi-tenant onboarding.

### Workstream B — Security *(urgent, independent of data work)*

**F-B1 · C · Cross-tenant read leak.** `cube_question_summary_overall_by_item` has **RLS disabled and zero policies** — a single-school session can read all 3 schools' rows (68,548 rows exposed). Apply the existing idempotent migration `20260617120000` (ENABLE RLS + `service_role_full` + `tenant_iso_select`, identical to every other cube). Re-run the CFP-scoped authenticated leak test afterward (must return only CFP rows). **Verify the same table on prod.**

**F-B2 · C · PII exposure on backup tables.** `anon` + `authenticated` hold **ALL privileges incl. SELECT** on 27 RLS-off `*_bak`/`fix*`/`mrg_bak*` tables, **6 of which contain student PII**. These are historical rollback anchors (out of live scope). Immediate: `REVOKE ALL ON <each> FROM anon, authenticated`. Durable: once the misfiling fixes are confirmed stable, **DROP** them (they are named rollback anchors in the runbook). On prod, inventory `_premig`/`*_gai13bak`/`relbl_bak_*`/`mrg_bak_*`/`clean_bak_*`, revoke grants immediately, and move to a private `backups` schema (prod can't regenerate them, so keep as rollback but lock down).

### Workstream C — Pipeline structural fixes *(require rebuild; make rebuilds safe/deterministic)*

**F-C1 · C · PIPE · `dim_item` first-occurrence vs fact latest-export divergence → 29 orphan buckets.** `dim_item` dedupes each item to its **earliest** `assessment_date` bucket (notebook parity) while fact keeps the **latest-export** bucket; whenever an item was exported under two folders they disagree → 37 items point at minority/zero-fact buckets, **29 `subject_id` buckets (7,730 fact rows) have no `dim_item` row** and are unreachable from every report list. Fix: derive `dim_item.subject_id` from the same rows that survive the fact `latest_export` prune (rebuild `dim_item` from `fact_student_submission`, or apply the identical `latest_export` window in `dim_item.sql` before the first-occurrence dedupe). **Verify: every `dim_item.subject_id` has fact rows; orphan query returns 0.** *This single fix dissolves the orphan finding (F-C1 subsumes the 29-orphan group).*

**F-C2 · C · PIPE · `latest_export` partition omits grade/subject/session → durable twin prevention.** The `latest_export` `PARTITION BY` (`fact_student_submission.sql:159-162`) omits subject/grade/assessment_type/session, so cross-folder copies of one item survive as separate label buckets and (the known open bug) leave cross-band 1-student/0% remnants (e.g. CFP "Topic 8" Higher-Ed). Fix: **add `grade` (and reconsider subject/assessment_type/session)** to the partition key, or enforce one label-set per `item_id` via a majority/`dim_item` vote at fact build, with an export-ordering fallback when `file_name` is absent. *Note: the immediate twin data is corrected in F-D2; this is the durable prevention so rebuilds stop re-minting twins.*

**F-C3 · H · PIPE · `dim_question_data` retains conflicting vintages.** `dqd` accumulates every export vintage (label sets, question-number sets, answer keys) because the latest-export-wins fix was applied to **fact only**. Cube builds then pick display metadata (`correct_answer`, `total_points`, `question_no`, labels) via a vintage-blind `LATERAL … LIMIT 1 ORDER BY identifier`. Consequences: **594 grains with wrong displayed correct answer** (F-D-adjacent), duplicate `Question 2` rows, mixed labels on rebuild. Fix: apply latest-export-wins dedupe to `dim_question_data` (one row per `(school, question_id, position)`); as belt-and-suspenders, add `AND q.item_id = f_meta.item_id` to the cube's lateral join and prefer the `dqd` row whose `correct_answer` matches fact. **Rebuild cubes after.**

**F-C4 · M · PIPE · Same-name merge pools different questions.** The merge keys on `(subject_id, question_no)`, assuming `question_no ⇒ same question` across sections — false for **302 slots across 68 assessments** where sections got different question variants. A "Question N" row shows one section's text with stats blended from an unrelated question. Fix: guard the merge — only collapse across items when normalized question text (or `question_id`) matches; otherwise fall back to per-item question rows. Add the `n_distinct_texts > 1` exclusion predicate to the merge path.

**F-C5 · M · PIPE · Student name not canonicalized per uid.** 3 students carry two surnames (mid-year legal changes) across fact + `cube_user_summary`; `dim_student` picked a non-latest export for one. Fix: canonicalize `user_name` per `(school_id, user_uid)` to the latest-attempt name at fact build (or post-pass UPDATE), rebuild `cube_user_summary`, and make `dim_student` take the newest export vintage per uid.

**F-C6 · M · PIPE · `cube_user_summary` fan-out & `cube_standard_summary` alias double-count.** (a) `cube_user_summary` sums all-attempt / per-choice / per-position fan-out rows against a differently-scaled denominator — **latent today (columns unread)** but wrong (avg 2–7 pp off, some >100%) if any feature divides them. (b) `cube_standard_summary` SUMs raw fact rows per identifier, double-counting alias/parent-child codes (`AI.MA.912.*` + `MA.912.*`) — percentages fine, absolute totals ~2×, latent until totals are surfaced. Fix: either apply the same per-`(user,question,position,submission)` MAX pre-aggregation + latest-attempt dedupe used in `cube_question_summary`, or explicitly document/deprecate the score/total columns so no consumer divides/sums them. Verify against KPI baselines (`total_questions`/`total_standards` must not move).

### Workstream D — Data corrections *(express as override seeds; back up + confirm before mutating)*

**F-D1 · C · SRC · 12 misfiled assessments (10 known + 2 new).** Relabel subject/grade to the section-consistent values via the durable override mechanism, then rebuild cubes. **The 2 CFP Pre-Algebra "Topic 1" items (`7964065626`, `7964067882`) are new** — add them to `docs/audit/assessment_misfiling_audit.md`. **Correction to the existing doc:** the two "HW Spiral Review" 4th-Period copies (`7626433775`, `7628347421`) belong to **Grade 6**, not Grade 7 (the 2nd-Period copies are Grade 7) — the relabel target differs per section. Full list + evidence: `evidence/section-teacher-integrity.csv`, `evidence/STI-1-repro.csv`. *Confirm the Crestwell "Chapter 1 Test" grade dispute with the school (open case).* 

**F-D2 · C · SRC/PIPE · Twin/split assessments (17 split + 44 duplicate + 31 type-split + 4 name-variant).** Same assessment scattered across 2+ `subject_id`s by label drift (assessment_type flips incl. whitespace `'Lesson  Assessments'`, per-section renames, band/session vintage). Some have **disjoint** cohorts (each report shows half the class); some **overlap** with contradictory scores (double-counted in Math rollups). Fix per set: collapse fragment rows into the majority bucket's `subject_id`/labels (relabel/twin-merge pattern), mapping cross-item cases (Crestwell chapter-1) by `question_no`; for overlapping-student twins keep the newest vintage per student+question. Express as override seeds so F-C2's rebuild doesn't re-split them. Evidence: `evidence/twin-split-assessments.csv`, `evidence/twin_pairs.csv`. *The whitespace `'Lesson  Assessments'` case is fixed immediately by F-F1 normalization.*

**F-D3 · C · SRC · Crestwell staff/demo cluster (5 fake students).** "Instructor 1/2" sandbox sections with test accounts (`Misbah Shaikh`, a bogus Grade-2 "Chapter 1 Test", a phantom 72-row 2024-25 session) inflate distinct-headcount KPIs by up to 5. Fix: delete these items' rows from fact + dims + cubes (phantom-cleanup pattern), **or** add an ingest-time exclusion for sandbox section/instructor names. **Confirm with Crestwell/Edvance these are internal accounts before deleting.** Evidence: `evidence/sweep-Crestwell-0-F2.csv`.

**F-D4 · H · SRC · Impossible per-question points (74 rows, recv > poss).** Students show >100% (e.g. 120% on "5.2 Spelling Test", extremes 66/1, 11/1). Mixed cause: source multi-part export inconsistency; a subset are heal-step scale errors (see F-D5); zero-point extra-credit questions. Fix case-by-case on the ~12 items: cap `points_received` at possible or restore correct possible from `dqd`/legacy parquet; re-derive the 66/11 healed rows from backup; decide a consistent policy for `points_possible = 0` questions. Evidence: `evidence/score-sanity.csv`.

**F-D5 · L→M · PIPE · Heal-population re-audit (415 rows).** The phantom-cleanup+heal step inserted rows with NULL points (279) or points with NULL answer (136), one showing 6600%. **Important:** the "empty `file_name` = heal marker" premise is **false** (`file_name` is empty on 100% of fact rows — see §7). Re-derive the true heal population from the backup tables (`clean_bak_*`, `mrg_bak_*`, `relbl_bak_*`), audit against legacy parquet, backfill recoverable answer/points, delete unrecoverable NULL-points stubs, rescale the 66/11 rows. **Do not scope by `file_name`.**

**F-D6 · H · SRC · Questions in fact absent from `dim_question_data` (33 q / 15 items).** Submissions reference question ids the retained Question-Data export doesn't contain (mid-year re-authoring) → ghost rows with blank question no/text/type; 4 Crestwell questions entirely invisible. Fix: backfill `dqd` rows from any export vintage containing them (or synthesize minimal `question_no`/`total_points` from fact positions); decide whether the 4 `dqd`-only Crestwell questions should be pruned; add pipeline validation `fact.question_id ⊆ dqd per item`.

**F-D7 · M · SRC · `points_possible` (fact) vs `total_points` (`dqd`) mismatch (47 question-positions / ~20 items).** Teacher changed point values between export runs; latest-wins keyed on fact only. On "Chapter 6 Perimeter and Area" the class average mixes 1-pt and 3-pt scored students for one question. Fix: reconcile each pair to the newest-export authority, patch the losing table, add a pipeline QA diff. (11 Crestwell, 3 Athenian, 2 CFP items.)

**F-D8 · H · PIPE · Grading contradictions (triage, do NOT bulk-fix).** 3,605 questions where the *same answer* is graded both right and wrong (Athenian 2,292, CFP 975; Crestwell none). Must be triaged case-by-case: distinguish legitimate partial-credit/multi-blank (leave) from true regrade collisions (heal via latest-export/points reconciliation). Recommend a narrow, reviewed batch, not automation. Evidence: `evidence/p3_grading_contradictions.csv`.

### Workstream E — Standards data *(seed + regenerate)*

**F-E1 · C · SEED · `dim_standard` ILIKE identifier collisions (18,220 fact rows).** 44 codes have 2 identifiers/descriptions from substring alias matching; fact pins the lexically-smallest (polluted) identifier → wrong descriptions, pooled per-standard averages, undercounted standard totals. Fix: purge polluted alias rows (where the attached identifier's canonical code contradicts the `schoology_standard` trailing segment), regenerate from CASE/CPALMS via `refresh_standards.py` with **exact-match** alias synthesis, rebuild fact `identifier` + cubes. Validate: no `schoology_standard` maps to >1 identifier except legit parent/child (a–f sub-parts). Evidence: `evidence/standards-coverage-gaps.csv`.

**F-E2 · H · SRC · 264 real codes with no `dim_standard` row.** Retired/legacy framework codes (`ELA.6.RL.6.4.2`, `MA.5.MACC.5.NBT.1.3.b`, old `LA.*` 2007) → NULL identifier → questions invisible in standards reports (but still counted in question reports → inconsistent totals). Fix: add curated `dim_standard` rows (map to nearest current benchmark or synthesize alias rows), re-run fact identifier join + cubes. Alternatively fix tags at Schoology source per `docs/standards-alignment.md`.

**F-E3 · H · SEED · 279 `dim_standard` rows with NULL description (272 MAFS/LAFS).** Retired frameworks → blank description cells + no CPALMS link for older Athenian math. Fix: backfill the **24 referenced** codes first (retired-framework text is on CPALMS archive pages — extend `resolve_cpalms_links.py` to scrape description alongside link), then the rest opportunistically; rebuild cubes.

**F-E4 · M · SEED · HTML entities in strand/standard labels (33 items, 14,100 rows).** Report shows literal `Expressions &amp; Equations`. Fix: decode HTML entities in `dim_strand.strand` and `dim_standard.strand/description/cluster` (and fix `refresh_standards.py` to decode on ingest). **Decode display columns only — do NOT touch `strand_id`** (hash join key); no cube rebuild needed (cubes carry `strand_id`, not the label).

**F-E5 · L · SEED · `dim_standard` seed hygiene.** 3 exact duplicate alias rows + 27 junk numeric-only codes (`0.5`, `0.11`) with contradictory subject/strand. Fix: delete dups + junk from seed and live table; add `UNIQUE(identifier, schoology_standard)` and a code-format check to `refresh_standards.py`.

**F-E6 · M · SRC · Non-code category labels stored as standards (3).** `'Social Studies'`, `'Conventions'`, `'Development/organizaion of Ideas'` as "standards" → meaningless label in question detail, excluded from rollups. Fix: null out values that match no `dim_standard` code pattern at parse/staging, or map explicitly; low-touch alternative: filter bare-word standards from question-detail display.

**F-E7 · M · SRC (source-side, no data fix) · Coverage & off-grade tagging.** 481 zero-mapped + 86 **partially**-mapped assessments (260 questions silently absent — partial is worse, reports *look* complete); 64 off-grade tags on correctly-filed items (Grade-K test tagged `MA.2.*`). These are **teacher-tagging gaps at source**, not migration defects. Fix at Schoology per `docs/standards-alignment.md` (prioritize the 86 partial); **UI improvement:** surface an "N of M questions aligned" badge so partial coverage is visible rather than silently wrong.

### Workstream F — Hygiene / labels *(low risk; rebuild affected cubes)*

**F-F1 · H · HYG · `assessment_type` junk pollutes slicer & splits data.** `'2 sectionsAll Sections'` (parse leak), single-vs-double-space `'Lesson Assessments'` (the double-space twin holds an assessment's *main* data), `'Test'`/`'Chap Test'`/lowercase `'topic'`/`'Unit'` vs `'Unit Test'`. Fix: normalize at staging (trim/collapse whitespace) + override-map the junk values, then relabel fact/dim/cubes. **This immediately un-splits several F-D2 twin sets.** Evidence: `evidence/SH-3_assessment_type_hygiene.csv`.

**F-F2 · M · HYG · Section label integrity (25 format variants + 9 NULL-section items + 5 CFP cross-course labels).** Two export vintages write `'Sec <code>'` vs `'<course> <code>'`; 3,520 rows have NULL/empty section (invisible to section filter, splits assessments into named+blank groups); 5 CFP `section_nid`s carry another course's label (science item shown "in" an ELA section). Fix: normalize section strings at staging (map by `section_nid` → `dim_section.section_name`), backfill NULL from `dim_section`, add the `dim_section` fallback to `get_school_alignment_quality`, and `COALESCE` at the cube build so blank never reaches reports.

**F-F3 · M · HYG · Platform/admin accounts as instructors (94 items).** `'GAINS Admin'` (40) and observer `'Sitara Qalander'`/`'Sitara Shamsheer'` (56) appear in teacher filters and by-teacher bands. Fix: instructor-exclusion list applied when building `dim_item`/`dim_section.section_instructors` (or at the cube/repo split). **Confirm `Qalander == Shamsheer` (rename) with the customer before merging identities.**

**F-F4 · M · HYG · `grade_no`/`grade_sort` ordering.** `grade_no = RIGHT(grade,1)` yields `'d'` for Higher-Ed and `'2'` for `Regular 9–12` (collides with Grade 2); `grade_sort` unused so `Grade K` renders after Grade 8. Fix: order `list_grades`/`list_subjects` by `grade_sort` with explicit ranks for the bands; give the bands explicit `grade_no` (`'HE'`, `'912'`) if it's ever consumed.

**F-F5 · L · HYG · Item-name cosmetics (52).** Mojibake `?` for apostrophes/en-dashes, doubled spaces, typos (`'Pat 1'`, `'Assesment'`). Verified purely display (no slicer splits). Fix: one-off `?`→`'` UPDATE across fact/dim_item/dim_subject/dqd/cubes; collapse whitespace at staging. Keep verbatim only if strict legacy parity is preferred.

**F-F6 · L · HYG · dim_section stale name.** `'Section A'` vs renamed `'Section AB'` (2 Crestwell sections, 13 items). Fix: make `dim_section` build latest-snapshot-wins per `section_nid`.

**F-F7 · L · HYG · `'HS Alegra II'` typo — DECISION REQUIRED.** Deliberately mirrored from legacy `AbpSettings` (`subject_grade_overrides.sql:422`). Teachers see the misspelling. This is a **parity-vs-correctness decision** — needs your sign-off to deviate from legacy. If approved, fix the display value (also dormant `'Calculas'`) and relabel the 4 `subject_id`s.

### Workstream G — Guardrails (add so this can't silently recur)

- **G1** Regression test: 2-attempt fixture asserting all read paths return the latest attempt (guards F-A1/A2).
- **G2** Pipeline QA assertions after each build: `fact.question_id ⊆ dqd per item`; every `dim_item.subject_id` has fact rows (orphan=0); `fact.points_possible == dqd.total_points` per question-position; no `subject_id` bucket without a `dim_item`; `COUNT(DISTINCT identifier)` per `schoology_standard` ≤ 1 (except parent/child).
- **G3** Keep the Q12 multi-select invariant test (currently passes at 0) in the suite.
- **G4** Surface **skipped cubes loudly** — `runner.py isolate_cubes=True` logs-and-skips a failed cube, leaving it silently stale (same class as M5).
- **G5** RLS parity check: assert every cube/tenant table has `relrowsecurity` + a `tenant_iso_select` policy (guards F-B1).
- **G6** Deterministic final tiebreak on dedupe `ORDER BY`s (append a stable key) so exact-dup collapses are reproducible across rebuilds.

---

## 5. Verification Protocol (per phase)

1. **Snapshot** affected tables to `*_bak` before mutating; wrap changes in an explicit transaction.
2. **Backend sanity:** `cd backend && ./venv/bin/python -m ruff check app/ --fix && ./venv/bin/python -c "from app.main import app; print('OK')"`.
3. **Rebuild** only the affected layer (`transform-runner --tag …`), with `SET statement_timeout = 0` for cubes; `ANALYZE` between layers.
4. **KPI conservation:** re-run `project_kpi_baseline` anchors — Athenian must match legacy to the digit except where a fix intends movement; document every intended delta.
5. **Twin invariant** and **orphan=0** checks after C1/C2/D2.
6. **Teacher-visible validation through the tenant role** (Playwright/API, not service_role) for the retake, zero-poisoning, and misfiling fixes — confirm the numbers a teacher actually sees.
7. **Regression suite** (`backend/tests/reports`) green.

---

## 6. Production Replay

Prod has **no raw/staging** — never run the pipeline there (it would wipe data). For each data fix:
- Apply on **local**, verify, capture the exact scoped SQL.
- Replay to prod via **scoped local→prod sync** + **cubes-only rebuild** (`railway run --service backend`, `SET statement_timeout = 0`), per `docs/audit/fixes/02_assessment_misfiling_prod_runbook.md`, with a backed-up transaction and `*_bak` rollback anchors.
- **Code fixes (A) and the RLS migration (B1)** deploy normally and self-heal — do these on prod first for fast wins.
- **F-B2/prod backup lockdown** must be run against prod explicitly (revoke `anon`/`authenticated`, move to `backups` schema).
- Rotate the prod DB password if it was exposed during ops (per `project_prod_cube_staleness`).

---

## 7. Ruled Out — do NOT spend effort here

These were flagged by a detector but **overturned on independent reproduction/refutation**:

- **`latest_export` prune is NOT inoperative.** Although fact's stored `file_name` is 100% empty, the prune runs at **build time on staging** (which has `file_name`, 100% parseable); the NULL-timestamp fallback never fires. The "prune is a no-op / safety net can't operate" claim is **false**. *Consequence: any finding scoped by `file_name` in the live fact table (e.g. the 415-row heal population) has an invalid basis — re-derive from backup tables (F-D5).*
- **Cross-bucket pruning "erases whole grade bands" (19 buckets) — harm overstated.** The mechanism (partition omits grade/subject) is real and worth hardening (F-C2), but the "~305 students lost" harm did not hold up; only a single 1-student Higher-Ed remnant is user-visible.
- **`dim_teacher` empty is by design**, not a bug — it has zero consumers; teacher identity everywhere is the `section_instructors` string. (The *drift* in those strings is real → F-F3.)
- **6 Crestwell `course_nid`s missing from `dim_course`** — refuted; not a migration gap and not causing blank headers as claimed.
- **Higher-Ed banding, CFP course-name subjects, Crestwell "Reading", Grade-8 Algebra with `.912` standards, Civics/Grade-8 using `SS.7` codes, week-1 review one grade down, 2 CFP accelerated students** — all **legitimate/by-design**, correctly excluded from misfiling.
- **"Latest-attempt-wins drops a higher earlier attempt" (91 cells, ~63 pts)** — faithful to legacy "latest attempt" semantics; only fix if you decide policy should be "best attempt" (§8).

---

## 8. Open Questions — need your / the customer's answer before those fixes

1. **CFP Higher-Ed band** — is it intentional dual-enrollment/honors grouping? (46 items). Confirm → document convention, exclude from misfiling heuristics.
2. **`Sitara Qalander` == `Sitara Shamsheer`?** (rename across years) — needed before merging instructor identity (F-F3).
3. **Crestwell staff/demo accounts** — confirm the 5 are internal test accounts before deletion (F-D3).
4. **Crestwell "Chapter 1 Test" grade** — Grade 1 vs Grade 2 dispute (open case in F-D1).
5. **`'HS Alegra II'` typo** — fix (deviate from legacy) or keep for parity? (F-F7).
6. **Attempt policy** — "latest attempt" (current, legacy-faithful) or "best/highest attempt"? Governs F-A1 tiebreak direction and the 91-cell case.
7. **`Amora Johnson`** in two schools — confirm two distinct children (no action expected; F-cosmetic).

---

## Appendix — Finding index & evidence

- Machine-readable: `audit_findings.json` (all 70 result rows with status/severity/class/root-cause/fix/evidence path).
- Evidence CSVs: `evidence/` — key files: `section-teacher-integrity.csv` & `STI-1-repro.csv` (12 misfiles), `twin-split-assessments.csv` / `twin_pairs.csv` (twins), `referential-orphans_*.csv` (orphans), `score-sanity.csv` (points/retakes), `standards-coverage-gaps.csv` (standards), `question-structure-anomalies.csv` (merge/dqd), `cube-vs-fact-drift.csv` (staleness), `pipeline-code-audit.csv` (code line refs), `p3_grading_contradictions.csv` (F-D8).
- Confirmed-finding tally: **45 confirmed** (18 critical, 20 high, rest medium/low across the workstreams above) + **20 probe findings** (security + retake corroboration) + **4 ruled benign** + **1 not reproduced**.
