# HMH ingestion — known issues, the fix options, and trade-offs

Scope: issues found while building/reviewing HMH-curriculum ingestion (branch `worktree-hmh-export-ingestion`). The core feature works and existing Schoology tenants are provably untouched; this doc records the open issues, what causes them, the suggested fixes, and the pros/cons — so a fix can be scheduled deliberately, not rushed.

---

## Issue 1 (the one that conflicts with existing data) — cluster + benchmark standards collapse

### What happens
HMH tags assessment items to **both** a B.E.S.T. *cluster* code (`MA.7.AR.1`) and its child *benchmark* (`MA.7.AR.1.1`) in the same assessment. In GAINS's standards reference list (`supabase/seeds/dim_standard.csv`), several clusters **share one internal identifier with a benchmark child** — e.g. both `MA.7.AR.1` and `MA.7.AR.1.1` carry identifier `3c642b67-…`. Any report that groups by identifier therefore treats the two distinct codes as one standard.

Observed on the HMH sample (grade-7 "Getting Ready for FSA Practice Test 2", 3 students):
- `cube_standard_summary.total_standards` = **29**, but the assessment actually carries **32 distinct standard codes** → the same assessment reports two different "Number of Standards" values.
- A merged row shows a **pooled grade-average** (e.g. 33.3%) that matches **neither** of the two real standards (25% and 50%).
- Confirmed collapsing pairs in the sample: AR.1/AR.1.1, AR.2/AR.2.1, DP.1/DP.1.5, DP.2/DP.2.x, GR.1/GR.1.x.

### What is NOT affected
- **Scores/points are correct.** The per-standard points are disjoint and sum exactly to HMH's own "Overall" total (verified to the penny). This is a count/label defect, not a scoring error.
- **The prominent per-assessment reports are correct.** Standards Deep Dive shows all **32** codes separately; Standard Summary shows all **41** school-wide standard cards separately. The collapse is confined to the identifier-keyed `cube_standard_summary` count.

### Root cause
Pre-existing data in `dim_standard.csv`: a cluster and one of its benchmarks were assigned the **same** identifier. This predates HMH. **Schoology assessments rarely tag both a cluster and its child in one assessment, so it never surfaced** — HMH's dual tagging is simply the first thing to exercise the latent seed error.

### Why it is NOT patched inside this HMH work
It is **unsafe to fix mechanically here**: existing Schoology tenants also reference cluster codes (**Athenian 15,552** and **Crestwell 819** fact rows). Changing those shared identifiers in the global seed would orphan existing-tenant facts — i.e. it would risk breaking schools that are live today. A safe fix is a **global, all-tenant, owner-gated operation**, not a parser patch.

### Suggested fix

**Option A (recommended) — correct the standards reference data.**
Give each affected cluster its own **distinct, real CPALMS identifier** (fetch the correct GUID from the CASE endpoint, the same way `MA.6.AR.3` was added correctly), update `dim_standard.csv`, reload `dim_standard`, then **rebuild facts for all tenants** so every school picks up the corrected identifiers.
- **Pros:** correct data model (a cluster and a benchmark *are* distinct standards); counts become consistent (32, not 29); no more blended averages; fixes the latent issue for **every** tenant, not just HMH.
- **Cons:** touches shared global data → must rebuild all tenants' facts (a large, scheduled, owner-approved job with a maintenance window); requires fetching/verifying the correct CPALMS GUID for each affected cluster; must confirm no existing report number moves unexpectedly (re-run the report-parity + fingerprint checks before/after).

**Option B — make the reports internally consistent instead of fixing the data.**
Make every rollup group by the same key (all by code, or all by identifier) and label "Number of Standards" accordingly.
- **Pros:** no seed/data change; smaller and lower-risk; removes the 29-vs-32 disagreement.
- **Cons:** does not fix the underlying wrong model — two distinct standards can still appear as one with a blended average; it is a labeling compromise; still needs an owner decision on whether a cluster counts as "a standard."

**Recommendation:** Option A, scheduled as a separate standards-data-maintenance task with owner sign-off, an all-tenant rebuild, and before/after verification. Low-risk when done carefully; just not something to bundle into the HMH feature.

---

## Other known limitations (by design or latent — not conflicts with existing data)

- **Blank "which wrong answer did they pick" reports.** HMH's export carries scores only — never the chosen answer, answer key, or option breakdown. So Incorrect Answer Details shows a clean "No answer-choice data" empty state, and QRA's distractor/answer columns are blank. This is HMH's data ceiling, not a bug; it only unlocks via HMH's (Okta-gated) API/Learnosity or by running the assessment natively in Schoology.
- **Schoology-worded remediation hint.** If a future HMH export ever carries an unresolved standard code, the alignment report would show a Schoology-specific instruction ("Open in Schoology → Align Learning Objective…") to an HMH school. Latent today — all sample codes resolve. A proper fix needs a per-tenant "source" indicator to vary the hint wording.
- **Custom (teacher-authored) assessments are invisible.** HMH omits non-standard-tagged custom assessments from the export at source, so GAINS shows nothing for them. GAINS coverage = HMH's B.E.S.T.-tagged program assessments only.
- **Viewer access.** A school-scoped user needs an access grant (`user_schools` membership) to see the HMH tenant in the school switcher; super-admins can scope to it via `?school_id=` without a grant.
- **Unused mis-weighted cube columns.** `cube_user_summary`'s `*_by_item`/`_by_section`/`_by_standard` possible-point columns assume Schoology's uniform 1-point questions and would mis-weight HMH's variable per-standard points — but they currently have **zero readers**, so no live impact. Correct or comment before anything consumes them.
