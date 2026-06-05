"""Per-item self-consistency invariants across multiple Athenian assessments.

WHY THIS EXISTS
---------------
``test_canonical_kpis.py`` pins exact legacy values for two specific items
(``8359960427`` + ``7892351049``). That guards the *numbers* for those two,
but a regression in the rollup-grain fix (commit ``85601ec`` — "source
standard/strand rollups from cqso grain") could drift on *other* assessments
while leaving the two pinned ones intact.

A true legacy-number diff across all items is **blocked**: the legacy backup
cubes key on salted SHA-256 hashes (``Subject_ID`` / ``ID`` / ``uKey`` are
hashes), so they cannot be joined back to the raw ``item_id``. We therefore
cannot compare modern per-item numbers to legacy per-item numbers in bulk —
documented explicitly here so nobody re-attempts that comparison.

Instead this module asserts the cross-checks that must hold for ANY correct
item, across several more Athenian assessments, locking the rollup grain
against multi-assessment drift:

  1. KPI ``total_students`` / ``total_questions`` exactly match
     ``cube_school_summary`` (the legacy school-level subtotal cube).
  2. ``sum(strand.num_standards) == len(standards_rollup) ==
     kpis.total_standards`` — the central rollup-grain guarantee. A strand
     column that under/over-counts vs. the standards table (the bug
     ``85601ec`` fixed) trips this.
  3. QRA and SDD report identical KPIs and identical per-strand
     ``num_standards`` for the same item — neither report may diverge.
  4. Each strand ``grade_average`` (where the strand is assessed) exactly
     reproduces ``AVERAGE(cube_question_summary_overall.grade_average)`` over
     the cqso rows whose Schoology standard rolls up to that strand — the
     exact grain ``get_strand_rollup_for_item`` is supposed to compute. This
     is the per-item reproduction of the legacy
     ``Grade_Average_Strand_Measure`` DAX.
  5. Grade bounds sanity: every non-null rollup grade sits in ``[0, 1]``.

The four items below were chosen because they are *aligned* (real strands /
standards, not the synthetic ``Other`` bucket) and span the interesting
shapes: single-strand single-standard, single-strand multi-standard,
multi-strand, and an item with an unassessed-alias (NULL-grade) strand.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.schemas.reports import (
    QuestionResponseAnalysisPayload,
    StandardsDeepDivePayload,
)

try:
    import psycopg2
except ImportError:  # pragma: no cover
    psycopg2 = None  # type: ignore[assignment]


_DB_DSN = "postgresql://postgres:postgres@127.0.0.1:56322/postgres"

# Aligned Athenian items beyond the two pinned in test_canonical_kpis.py.
# (item_id, shape note) — all verified `alignment_status == "full"`.
_MULTI_ITEMS = [
    "7892356634",  # 1 strand / 1 standard / 39 students / 35 q
    "7892356891",  # 1 strand / 2 standards / 24 students / 30 q
    "7892353570",  # 2 strands (one NULL-grade alias) / 22 students / 10 q
    "7892350647",  # 1 strand / 5 standards / 21 students / 20 q
]


async def _get_qra(client: AsyncClient, item_id: str) -> QuestionResponseAnalysisPayload:
    response = await client.get(
        f"/api/v1/reports/question-response-analysis/{item_id}"
    )
    if response.status_code == 404:
        pytest.skip(f"Item {item_id} missing — pipeline not seeded for this DB.")
    assert response.status_code == 200, response.text
    return QuestionResponseAnalysisPayload.model_validate(response.json())


async def _get_sdd(client: AsyncClient, item_id: str) -> StandardsDeepDivePayload:
    response = await client.get(f"/api/v1/reports/standards-deep-dive/{item_id}")
    if response.status_code == 404:
        pytest.skip(f"Item {item_id} missing — pipeline not seeded for this DB.")
    assert response.status_code == 200, response.text
    return StandardsDeepDivePayload.model_validate(response.json())


def _connect():
    if psycopg2 is None:
        pytest.skip("psycopg2 not installed — cannot read cube for cross-check.")
    try:
        conn = psycopg2.connect(_DB_DSN)
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"Local seeded DB unavailable ({exc}).")
    conn.autocommit = True
    return conn


def _cube_school_counts(item_id: str) -> tuple[int, int] | None:
    conn = _connect()
    try:
        with conn.cursor() as c:
            c.execute("SET row_security = off")
            c.execute(
                "SELECT total_students, total_questions "
                "FROM cube_school_summary WHERE item_id = %s",
                (item_id,),
            )
            row = c.fetchone()
    finally:
        conn.close()
    return (int(row[0]), int(row[1])) if row else None


def _cube_strand_grade(item_id: str, strand: str) -> float | None:
    """Reproduce ``get_strand_rollup_for_item``'s grade grain from the cube.

    ``AVG(cqso.grade_average)`` over the cqso rows whose Schoology standard
    (joined via ``dim_standard.schoology_standard``) rolls up to ``strand``,
    restricted to the standards this item actually used. Mirrors the repo
    method's ``AVERAGE('cube_question_summary_overall'[Grade_Average])`` DAX
    so the API value must equal it exactly.
    """
    conn = _connect()
    try:
        with conn.cursor() as c:
            c.execute("SET row_security = off")
            c.execute(
                """
                WITH subj AS (
                    SELECT DISTINCT subject_id FROM cube_question_summary
                    WHERE item_id = %s AND subject_id IS NOT NULL
                ),
                item_codes AS (
                    SELECT DISTINCT standard AS code FROM dim_question_data
                    WHERE item_id = %s
                      AND standard IS NOT NULL AND standard NOT IN ('', 'null')
                )
                SELECT AVG(cqso.grade_average)
                FROM cube_question_summary_overall cqso
                JOIN subj s ON s.subject_id = cqso.subject_id
                JOIN dim_standard ds ON ds.schoology_standard = cqso.standards
                JOIN item_codes ic ON ic.code = cqso.standards
                WHERE ds.strand = %s
                """,
                (item_id, item_id, strand),
            )
            row = c.fetchone()
    finally:
        conn.close()
    return float(row[0]) if row and row[0] is not None else None


@pytest.mark.anyio
@pytest.mark.parametrize("item_id", _MULTI_ITEMS)
async def test_multi_kpi_counts_match_cube_school_summary(
    admin_client: AsyncClient, item_id: str
) -> None:
    """KPI student/question counts must equal the school-level cube exactly."""
    sdd = await _get_sdd(admin_client, item_id)
    counts = _cube_school_counts(item_id)
    if counts is None:
        pytest.skip(f"No cube_school_summary row for {item_id}.")
    students, questions = counts
    assert sdd.kpis.total_students == students, (
        f"{item_id}: KPI total_students {sdd.kpis.total_students} != "
        f"cube_school_summary {students}"
    )
    assert sdd.kpis.total_questions == questions, (
        f"{item_id}: KPI total_questions {sdd.kpis.total_questions} != "
        f"cube_school_summary {questions}"
    )


@pytest.mark.anyio
@pytest.mark.parametrize("item_id", _MULTI_ITEMS)
async def test_multi_strand_column_sums_to_standards_table_and_kpi(
    admin_client: AsyncClient, item_id: str
) -> None:
    """sum(strand.num_standards) == len(standards_rollup) == total_standards.

    The central guarantee of the rollup-grain fix (85601ec). If the strand
    column counts a different grain than the standards table, this trips.
    """
    sdd = await _get_sdd(admin_client, item_id)
    sum_ns = sum(s.num_standards for s in sdd.strands_rollup)
    assert sum_ns == len(sdd.standards_rollup), (
        f"{item_id}: sum(strand.num_standards)={sum_ns} != "
        f"len(standards_rollup)={len(sdd.standards_rollup)}"
    )
    assert sum_ns == sdd.kpis.total_standards, (
        f"{item_id}: sum(strand.num_standards)={sum_ns} != "
        f"kpis.total_standards={sdd.kpis.total_standards}"
    )


@pytest.mark.anyio
@pytest.mark.parametrize("item_id", _MULTI_ITEMS)
async def test_multi_qra_sdd_parity(
    admin_client: AsyncClient, item_id: str
) -> None:
    """QRA and SDD must agree on every KPI and per-strand num_standards."""
    qra = await _get_qra(admin_client, item_id)
    sdd = await _get_sdd(admin_client, item_id)

    assert qra.kpis.total_students == sdd.kpis.total_students, item_id
    assert qra.kpis.total_questions == sdd.kpis.total_questions, item_id
    assert qra.kpis.total_standards == sdd.kpis.total_standards, item_id
    assert round(qra.kpis.grade_average, 6) == round(sdd.kpis.grade_average, 6), item_id
    assert qra.kpis.grade_average_pct == sdd.kpis.grade_average_pct, item_id

    qra_ns = {s.strand: s.num_standards for s in qra.strands_rollup}
    sdd_ns = {s.strand: s.num_standards for s in sdd.strands_rollup}
    assert qra_ns == sdd_ns, (
        f"{item_id}: QRA/SDD per-strand num_standards diverged.\n"
        f"QRA: {qra_ns}\nSDD: {sdd_ns}"
    )


@pytest.mark.anyio
@pytest.mark.parametrize("item_id", _MULTI_ITEMS)
async def test_multi_strand_grade_reproduces_cqso_average(
    admin_client: AsyncClient, item_id: str
) -> None:
    """Each assessed strand grade == AVG(cqso.grade_average) for that strand.

    Reproduces the legacy ``Grade_Average_Strand_Measure`` DAX grain that
    ``get_strand_rollup_for_item`` computes. Strands whose only standards
    are unassessed aliases carry a NULL grade (legacy blank cell) and are
    skipped from the equality check but still validated as None on both
    sides.
    """
    sdd = await _get_sdd(admin_client, item_id)
    assert sdd.strands_rollup, f"{item_id}: expected aligned strands, got none."

    checked_any = False
    for st in sdd.strands_rollup:
        cube = _cube_strand_grade(item_id, st.strand)
        if st.grade_average is None:
            # Unassessed-alias strand → legacy renders blank; cube agrees.
            assert cube is None, (
                f"{item_id}: strand {st.strand!r} API grade is None but cube "
                f"AVG(cqso)={cube} — blank-cell semantics broke."
            )
            continue
        assert cube is not None, (
            f"{item_id}: strand {st.strand!r} API grade={st.grade_average} but "
            f"cube AVG(cqso) is None — rollup sourced from the wrong grain."
        )
        assert round(st.grade_average, 6) == round(cube, 6), (
            f"{item_id}: strand {st.strand!r} grade {st.grade_average} != "
            f"cube AVG(cqso.grade_average) {cube} — rollup grain drifted "
            f"(regression of 85601ec)."
        )
        checked_any = True

    assert checked_any, (
        f"{item_id}: no assessed strand had a reproducible grade — fixture "
        f"changed; re-pick the item."
    )


@pytest.mark.anyio
@pytest.mark.parametrize("item_id", _MULTI_ITEMS)
async def test_multi_rollup_grade_bounds(
    admin_client: AsyncClient, item_id: str
) -> None:
    """Every non-null rollup grade is a valid proportion in [0, 1]."""
    sdd = await _get_sdd(admin_client, item_id)
    for s in sdd.standards_rollup:
        if s.grade_average is not None:
            assert 0.0 <= s.grade_average <= 1.0, (
                f"{item_id}: standard {s.schoology_standard!r} grade "
                f"{s.grade_average} out of [0,1]."
            )
    for s in sdd.strands_rollup:
        if s.grade_average is not None:
            assert 0.0 <= s.grade_average <= 1.0, (
                f"{item_id}: strand {s.strand!r} grade {s.grade_average} "
                f"out of [0,1]."
            )
    assert 0.0 <= sdd.kpis.grade_average <= 1.0, item_id
