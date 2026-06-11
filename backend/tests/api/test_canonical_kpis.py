"""Regression tests for the canonical, source-of-truth KPI helper.

These tests pin hard expected values for two specific Athenian assessments
in the local pipeline-seeded DB so that QRA, SDD, and any future
per-assessment report cannot silently drift from the canonical
per-(user, question) collapse semantics.

═══════════════════════════════════════════════════════════════════════════
ANCHOR PROVENANCE — seed=42 / limit-per-school=100
───────────────────────────────────────────────────────────────────────────
The expected values below are tied to the deterministic clean rebuild::

    gains_data ingest --school ALL --limit-per-school 100 --seed 42

The previous anchor item (``8359960427``, Chapter 9 Test) is NOT in this
sample, so it was replaced with two Athenian assessments that ARE present
and carry the most students. EVERY pinned number here was computed directly
from the live DB using the SAME SQL the report service runs
(``CubeRepository.get_canonical_kpis_for_item`` /
``get_strand_rollup_for_item`` / ``get_standard_rollup_for_item``) and
cross-checked against the live QRA + SDD endpoints.

IF THE SAMPLE CHANGES (different seed, different limit, re-ingest) these
anchors MUST be regenerated. Recompute by replaying the canonical KPI SQL
for the chosen items against the rebuilt DB and update the constants below.

Both fixture items are Athenian: the test ``admin_client`` is a super-admin
with no membership, so RLS scopes it to the Athenian fallback tenant
(``DEFAULT_SCHOOL_BUILDING_ID=186370968``). Items from other schools would
return 404 under this fixture.
═══════════════════════════════════════════════════════════════════════════

The contract being defended (see
``.hermes/report-parity/FRESH-RCA-2026-05-18-stable-formulas.md`` §4):

* ``total_students``  — exact match to the deterministic primary-subject
  pick in ``cube_school_summary``.
* ``total_questions`` — exact ``DISTINCTCOUNT(question_no)`` over the
  per-(user, question) collapsed fact.
* ``total_standards`` — exact ``COUNT(DISTINCT standard)`` over
  ``dim_question_data`` for the item (raw long-form labels), which equals
  the ``standards_rollup`` row count and the sum of per-strand
  ``num_standards``.
* ``grade_average / grade_min / grade_max`` — per-(user, question)
  collapsed grades averaged per question, then AVG / MIN / MAX across
  questions.
* ``standards_rollup`` row count — equals the number of distinct
  ``schoology_standard`` codes the item's standards resolve to.

Two fixture items are pinned:

* ``7892346396`` (Athenian, 40 students / 42 questions / 12 standards):
  grade_average ≈ 72.6% / high 100% / low 32.5%. Rich multi-strand item;
  the primary anchor.
* ``7338178174`` (Athenian, 30 students / 13 questions / 6 standards):
  grade_average ≈ 68.7% / high 96.7% / low 6.7%. Secondary control item;
  asserts QRA/SDD lock-step on a different, smaller assessment.

NOTE — legacy bulk diff is blocked. The legacy backup cubes key on salted
SHA-256 hashes (``Subject_ID`` / ``ID`` / ``uKey`` are hashes), so they
cannot be joined back to the raw ``item_id``; a per-item modern-vs-legacy
number diff across all assessments is impossible. ``test_canonical_kpis_multi.py``
therefore locks the rollup grain on *additional* assessments via internal
self-consistency invariants (cube-count match, strand-column ==
standards-table == KPI, QRA/SDD parity, strand grade == AVG(cqso)) rather
than a legacy diff.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.schemas.reports import (
    QuestionResponseAnalysisPayload,
    StandardsDeepDivePayload,
)


# ── Anchors tied to seed=42 / limit-per-school=100 (see module docstring).
#    Regenerate from the live DB if the ingest sample changes.
_PRIMARY_ITEM_ID = "7892346396"   # Athenian, 40 students / 42 questions / 12 standards
_CONTROL_ITEM_ID = "7338178174"   # Athenian, 30 students / 13 questions / 6 standards


async def _get_qra(client: AsyncClient, item_id: str) -> QuestionResponseAnalysisPayload:
    response = await client.get(
        f"/api/v1/reports/question-response-analysis/{item_id}"
    )
    if response.status_code == 404:
        pytest.skip(f"Item {item_id} missing — pipeline not seeded for this DB.")
    assert response.status_code == 200, response.text
    return QuestionResponseAnalysisPayload.model_validate(response.json())


async def _get_sdd(client: AsyncClient, item_id: str) -> StandardsDeepDivePayload:
    response = await client.get(
        f"/api/v1/reports/standards-deep-dive/{item_id}"
    )
    if response.status_code == 404:
        pytest.skip(f"Item {item_id} missing — pipeline not seeded for this DB.")
    assert response.status_code == 200, response.text
    return StandardsDeepDivePayload.model_validate(response.json())


@pytest.mark.anyio
async def test_canonical_kpis_primary_counts_exact(
    admin_client: AsyncClient,
) -> None:
    """KPI counts must exactly match the canonical values for the primary item.

    ``total_students`` comes from the deterministic primary-subject pick in
    ``cube_school_summary``; ``total_questions`` from the per-(user, question)
    fact collapse; ``total_standards`` from ``COUNT(DISTINCT standard)`` over
    ``dim_question_data`` (raw long-form labels).
    """
    qra = await _get_qra(admin_client, _PRIMARY_ITEM_ID)

    assert qra.kpis.total_students == 40, (
        f"Total Students must equal 40, got {qra.kpis.total_students}"
    )
    assert qra.kpis.total_questions == 42, (
        f"Total Questions must equal 42 (per-user collapse DISTINCTCOUNT), "
        f"got {qra.kpis.total_questions}"
    )
    assert qra.kpis.total_standards == 12, (
        f"Total Standards must equal 12 — counts raw standards labels per "
        f"COUNT(DISTINCT standard) — got {qra.kpis.total_standards}"
    )
    assert qra.kpis.total_possible_point == 4470.0, (
        f"Total Possible must equal 4470.0, got {qra.kpis.total_possible_point}"
    )
    assert qra.kpis.total_score == 2863.0, (
        f"Total Score must equal 2863.0, got {qra.kpis.total_score}"
    )


@pytest.mark.anyio
async def test_canonical_kpis_primary_percentages_exact(
    admin_client: AsyncClient,
) -> None:
    """Grade Average / Highest / Lowest must match the canonical collapse.

    Computed per-(user, question) → per-question average → AVG/MIN/MAX
    across questions, then rounded to 6 dp by the service. Values pinned
    to the seed=42 sample.
    """
    qra = await _get_qra(admin_client, _PRIMARY_ITEM_ID)

    assert qra.kpis.grade_average == 0.72631, (
        f"Grade Average must equal canonical 0.72631, "
        f"got {qra.kpis.grade_average}"
    )
    assert qra.kpis.grade_average_pct == "72.6%", (
        f"Grade Average pct must render 72.6%, got {qra.kpis.grade_average_pct}"
    )
    assert qra.kpis.grade_max == 1.0, (
        f"Overall Highest must equal 1.0 (a fully-correct question), "
        f"got {qra.kpis.grade_max}"
    )
    assert qra.kpis.grade_min == 0.325, (
        f"Overall Lowest must equal canonical 0.325, got {qra.kpis.grade_min}"
    )


@pytest.mark.anyio
async def test_canonical_kpis_qra_sdd_parity_primary(
    admin_client: AsyncClient,
) -> None:
    """QRA and SDD must report IDENTICAL KPI values for the same item.

    This is the central guarantee of the canonical helper. Any divergence
    here means the helper is bypassed or QRA / SDD diverged in service.
    """
    qra = await _get_qra(admin_client, _PRIMARY_ITEM_ID)
    sdd = await _get_sdd(admin_client, _PRIMARY_ITEM_ID)

    assert qra.kpis.total_students == sdd.kpis.total_students, (
        f"QRA total_students {qra.kpis.total_students} != "
        f"SDD total_students {sdd.kpis.total_students}"
    )
    assert qra.kpis.total_questions == sdd.kpis.total_questions, (
        f"QRA total_questions {qra.kpis.total_questions} != "
        f"SDD total_questions {sdd.kpis.total_questions}"
    )
    assert qra.kpis.total_standards == sdd.kpis.total_standards, (
        f"QRA total_standards {qra.kpis.total_standards} != "
        f"SDD total_standards {sdd.kpis.total_standards}"
    )
    assert round(qra.kpis.grade_average, 6) == round(sdd.kpis.grade_average, 6), (
        f"QRA grade_average {qra.kpis.grade_average} != "
        f"SDD grade_average {sdd.kpis.grade_average}"
    )
    assert qra.kpis.grade_average_pct == sdd.kpis.grade_average_pct, (
        f"QRA grade_average_pct {qra.kpis.grade_average_pct} != "
        f"SDD grade_average_pct {sdd.kpis.grade_average_pct}"
    )


@pytest.mark.anyio
async def test_canonical_standards_rollup_primary_exact_12_rows(
    admin_client: AsyncClient,
) -> None:
    """Standards rollup table must render the 12 canonical standards.

    The item's 12 distinct standards each resolve to their own
    ``schoology_standard`` row via the exact-match join in
    ``get_standard_rollup_for_item``; row count = 12.
    """
    sdd = await _get_sdd(admin_client, _PRIMARY_ITEM_ID)

    assert len(sdd.standards_rollup) == 12, (
        f"Standards rollup must have exactly 12 rows, "
        f"got {len(sdd.standards_rollup)}: "
        f"{[r.schoology_standard for r in sdd.standards_rollup]}"
    )

    schoology = {r.schoology_standard for r in sdd.standards_rollup}
    # The 12 canonical codes this item's standards resolve to (seed=42).
    expected_schoology = {
        "ELA.6.C.3.1",
        "ELA.K12.EE.1.1",
        "ELA.K12.EE.3.1",
        "ELA.6.R.1.1",
        "ELA.6.R.1.2",
        "ELA.6.R.1.3",
        "ELA.6.R.1.4",
        "ELA.6.R.2.2",
        "ELA.6.R.2.3",
        "ELA.6.R.3.3",
        "ELA.6.V.1.2",
        "ELA.6.V.1.3",
    }
    assert schoology == expected_schoology, (
        f"Standards rollup set drifted from expected 12. "
        f"Missing: {expected_schoology - schoology}. Extra: {schoology - expected_schoology}."
    )


@pytest.mark.anyio
async def test_canonical_strands_rollup_primary_exact_4_strands(
    admin_client: AsyncClient,
) -> None:
    """Strand rollup must render the 4 canonical strands for the primary item."""
    sdd = await _get_sdd(admin_client, _PRIMARY_ITEM_ID)

    assert len(sdd.strands_rollup) == 4, (
        f"Strand rollup must have exactly 4 rows, "
        f"got {len(sdd.strands_rollup)}: "
        f"{[r.strand for r in sdd.strands_rollup]}"
    )
    strands = {r.strand for r in sdd.strands_rollup}
    assert strands == {"Communication", "Expectations", "Reading", "Vocabulary"}, (
        f"Strand set drifted: {strands}"
    )


@pytest.mark.anyio
async def test_canonical_strand_num_standards_matches_table_grain(
    admin_client: AsyncClient,
) -> None:
    """Per-strand ``num_standards`` must sum to the school-level KPI.

    The strand column counts ``DISTINCT schoology_standard`` per strand
    from the same ``labeled`` CTE that drives the standards rollup,
    guaranteeing the strand column always sums to the standards-table row
    count and the school-level KPI (regression guard against the
    identifier-grain undercount fixed 2026-05-19).
    """
    sdd = await _get_sdd(admin_client, _PRIMARY_ITEM_ID)

    # Structural: strand sum == standards table count == KPI.
    sum_per_strand = sum(s.num_standards for s in sdd.strands_rollup)
    assert sum_per_strand == len(sdd.standards_rollup), (
        f"sum(strand.num_standards) = {sum_per_strand} must equal "
        f"len(standards_rollup) = {len(sdd.standards_rollup)} — strand "
        f"column and standards table disagree on visible standard count."
    )
    assert sum_per_strand == sdd.kpis.total_standards, (
        f"sum(strand.num_standards) = {sum_per_strand} must equal "
        f"kpis.total_standards = {sdd.kpis.total_standards} — strand "
        f"column and KPI tile disagree."
    )
    assert sum_per_strand == 12, (
        f"total_standards should be 12, got {sum_per_strand}."
    )

    # Per-strand pin (schoology_standard grain from the labeled CTE).
    expected_per_strand = {
        "Communication": 1,   # ELA.6.C.3.1
        "Expectations": 2,    # ELA.K12.EE.1.1, ELA.K12.EE.3.1
        "Reading": 7,         # ELA.6.R.{1.1,1.2,1.3,1.4,2.2,2.3,3.3}
        "Vocabulary": 2,      # ELA.6.V.{1.2,1.3}
    }
    actual_per_strand = {s.strand: s.num_standards for s in sdd.strands_rollup}
    assert actual_per_strand == expected_per_strand, (
        f"Per-strand num_standards drifted.\n"
        f"Expected: {expected_per_strand}\nActual: {actual_per_strand}"
    )


@pytest.mark.anyio
async def test_canonical_qra_strand_num_standards_matches_sdd(
    admin_client: AsyncClient,
) -> None:
    """QRA and SDD must agree on per-strand num_standards.

    Both reports consume ``_build_strand_standard_rollups`` which calls
    the same ``get_strand_rollup_for_item`` repo method. Asserts the
    structural guarantee that a future divergence between the two
    reports' strand tables is caught.
    """
    qra = await _get_qra(admin_client, _PRIMARY_ITEM_ID)
    sdd = await _get_sdd(admin_client, _PRIMARY_ITEM_ID)

    qra_per_strand = {s.strand: s.num_standards for s in qra.strands_rollup}
    sdd_per_strand = {s.strand: s.num_standards for s in sdd.strands_rollup}
    assert qra_per_strand == sdd_per_strand, (
        f"QRA and SDD strand num_standards diverged.\n"
        f"QRA: {qra_per_strand}\nSDD: {sdd_per_strand}"
    )


@pytest.mark.anyio
async def test_canonical_per_question_lowest_matches_kpi_lowest(
    admin_client: AsyncClient,
) -> None:
    """The lowest per-question grade must equal the canonical KPI Lowest.

    Q16 is the lowest-scoring question; its per-(user, question) collapsed
    grade (0.325) is the same grain as the KPI Lowest. If these disagree,
    the KPI strip and the question table render contradictory percentages
    for the same question.
    """
    qra = await _get_qra(admin_client, _PRIMARY_ITEM_ID)

    q16 = next(
        (q for q in qra.questions_overall if q.question_no == "16"),
        None,
    )
    assert q16 is not None, "Q16 missing from questions_overall"
    assert round(q16.grade_average, 6) == 0.325, (
        f"Q16 grade_average must equal the canonical Lowest KPI (0.325), "
        f"got {q16.grade_average}."
    )
    assert round(q16.grade_average, 6) == round(qra.kpis.grade_min, 6), (
        f"Q16 per-question grade {q16.grade_average} must equal KPI "
        f"grade_min {qra.kpis.grade_min}."
    )


@pytest.mark.anyio
async def test_canonical_per_question_q1_matches_raw(
    admin_client: AsyncClient,
) -> None:
    """Q1 must report its canonical per-(user, question) grade (0.675).

    Asserts the per-question table reflects the per-user collapse, not a
    cube row-grain SUM/SUM, on a non-extreme question.
    """
    qra = await _get_qra(admin_client, _PRIMARY_ITEM_ID)

    q1 = next(
        (q for q in qra.questions_overall if q.question_no == "1"),
        None,
    )
    assert q1 is not None, "Q1 missing from questions_overall"
    assert round(q1.grade_average, 6) == 0.675, (
        f"Q1 grade_average must equal canonical 0.675, got {q1.grade_average}."
    )


@pytest.mark.anyio
async def test_canonical_kpis_control_item_renders_cleanly(
    admin_client: AsyncClient,
) -> None:
    """Secondary control assessment must render without regression.

    Asserts the canonical helper handles a different, smaller item
    correctly and that QRA/SDD remain in lock-step on an assessment
    other than the primary anchor.
    """
    qra = await _get_qra(admin_client, _CONTROL_ITEM_ID)
    sdd = await _get_sdd(admin_client, _CONTROL_ITEM_ID)

    assert qra.kpis.total_students == 30
    assert qra.kpis.total_questions == 13
    assert qra.kpis.total_standards == 6
    assert qra.kpis.grade_average == 0.687179, (
        f"Control grade_average should equal 0.687179, "
        f"got {qra.kpis.grade_average}"
    )
    assert qra.kpis.grade_max == 0.966667, (
        f"Control grade_max should equal 0.966667, got {qra.kpis.grade_max}"
    )
    assert qra.kpis.grade_min == 0.066667, (
        f"Control grade_min should equal 0.066667, got {qra.kpis.grade_min}"
    )

    # Standards/strand grain consistency on the control item too.
    assert len(sdd.standards_rollup) == 6
    assert sum(s.num_standards for s in sdd.strands_rollup) == 6
    assert sum(s.num_standards for s in sdd.strands_rollup) == sdd.kpis.total_standards

    # Parity between QRA and SDD on the control.
    assert qra.kpis.total_students == sdd.kpis.total_students
    assert qra.kpis.total_questions == sdd.kpis.total_questions
    assert qra.kpis.total_standards == sdd.kpis.total_standards
    assert round(qra.kpis.grade_average, 6) == round(sdd.kpis.grade_average, 6)


@pytest.mark.anyio
async def test_canonical_kpis_helper_returns_nonzero_for_seeded_item(
    admin_client: AsyncClient,
) -> None:
    """Sanity guard: the canonical helper must not silently return zeros
    for a fully-seeded assessment. If grade_max == 0 with non-zero
    students, the per-question CTE collapsed everything to NULL —
    indicates the fact_dedup filter (points_possible > 0) is too
    aggressive or fact rows are missing.
    """
    qra = await _get_qra(admin_client, _PRIMARY_ITEM_ID)

    assert qra.kpis.grade_max > 0.0
    assert qra.kpis.grade_min > 0.0
    assert qra.kpis.grade_min <= qra.kpis.grade_average <= qra.kpis.grade_max
