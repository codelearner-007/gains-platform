"""Safety net: the Schoology course-prefix aliases must never be dropped.

WHY THIS EXISTS
---------------
The per-question standards rollups (Standards Deep Dive, Standard/Strand
Summary, QRA strand tables) join the *raw* label a Schoology assessment
emitted — ``dim_question_data.standard`` — to ``dim_standard`` via an
**exact** ``schoology_standard`` match (``cube_standard_summary`` /
``get_standard_rollup_for_item``). Schoology emits up to four parallel
``Standards`` columns per question, including course-prefix aliases such
as ``AI.MA.912.AR.3.1`` alongside the canonical ``MA.912.AR.3.1`` (see
``docs/audit/legacy-schoology-cpalms-mapping.md``). Those alias rows live
in ``supabase/seeds/dim_standard.csv`` only because legacy's Spark
pipeline observed them in the gradebook CSVs and unioned them in.

A future ``refresh_standards.py`` run that regenerates the seed purely
from CPALMS/CASE (the ``--full-pull`` path) would emit ONE row per IMS
leaf and silently DROP every ``AI.MA.*`` / ``*.MAFS.*`` alias row. The
exact-match join would then fall through for any assessment that aligned
to the alias form, dumping those questions into the synthetic ``Other``
bucket and quietly corrupting the rollups — with no error anywhere.

This test fails the moment that happens. It runs against the live seeded
DB and skips cleanly when the pipeline data is absent (CI without a
seeded warehouse).

WHAT IT ASSERTS
---------------
Every *standard-code-shaped* label actually used by an assessment
(``dim_question_data.standard``) has an exact match in
``dim_standard.schoology_standard``.

"Code-shaped" = contains a dot AND a digit (``AI.MA.912.AR.3.1``,
``MA.9-12.MAFS.912.N-RN.1.2``). This deliberately tolerates non-code junk
labels a teacher may have typed into a Standards column (e.g. the literal
``"Social Studies"`` currently present on three Athenian items), which
never had — and never will have — a ``dim_standard`` row and is surfaced
separately via the ``labels_not_mapped`` data-quality cause. We are
guarding against *regressions that lose real codes*, not pre-existing
data noise.
"""

from __future__ import annotations

import pytest

try:
    import psycopg2
except ImportError:  # pragma: no cover - psycopg2 always installed in backend venv
    psycopg2 = None  # type: ignore[assignment]


_DB_DSN = "postgresql://postgres:postgres@127.0.0.1:56322/postgres"

# A label is a real standard CODE (vs. a junk subject name) when it
# contains both a dot and a digit. Mirrors the cube's expectation that
# every aligned label is a dotted, numbered standard identifier.
_CODE_SHAPE_REGEX = r"\.[^.]*[0-9]|[0-9][^.]*\."


def _connect():
    if psycopg2 is None:
        pytest.skip("psycopg2 not installed — cannot run DB coverage check.")
    try:
        conn = psycopg2.connect(_DB_DSN)
    except Exception as exc:  # noqa: BLE001 - any connect failure → skip
        pytest.skip(f"Local seeded DB unavailable ({exc}); skipping coverage check.")
    conn.autocommit = True
    return conn


def _tables_present(cur) -> bool:
    cur.execute(
        """
        SELECT
          to_regclass('public.dim_question_data') IS NOT NULL
          AND to_regclass('public.dim_standard') IS NOT NULL
        """
    )
    return bool(cur.fetchone()[0])


def test_used_standards_have_exact_dim_standard_match() -> None:
    """No code-shaped assessment standard may lack its dim_standard alias.

    If this fails after a standards refresh, the refresh dropped one or
    more Schoology alias rows. Restore them (re-run the alias-augmentation
    step / restore ``dim_standard.csv.bak``) before reloading. See the
    module docstring and ``docs/standards-alignment.md`` §"Alias safety".
    """
    conn = _connect()
    try:
        with conn.cursor() as cur:
            if not _tables_present(cur):
                pytest.skip(
                    "dim_question_data / dim_standard not present — "
                    "pipeline not run for this DB."
                )

            cur.execute(
                """
                WITH used AS (
                    SELECT DISTINCT standard
                    FROM dim_question_data
                    WHERE standard IS NOT NULL
                      AND standard NOT IN ('', 'null', 'Other')
                )
                SELECT u.standard
                FROM used u
                WHERE u.standard ~ %s
                  AND NOT EXISTS (
                      SELECT 1 FROM dim_standard d
                      WHERE d.schoology_standard = u.standard
                  )
                ORDER BY u.standard
                """,
                (_CODE_SHAPE_REGEX,),
            )
            dropped = [r[0] for r in cur.fetchall()]

            # Also surface total used-code count so a skip-vs-empty DB is
            # obvious in the failure message.
            cur.execute(
                """
                SELECT count(*) FROM (
                    SELECT DISTINCT standard
                    FROM dim_question_data
                    WHERE standard IS NOT NULL
                      AND standard NOT IN ('', 'null', 'Other')
                      AND standard ~ %s
                ) t
                """,
                (_CODE_SHAPE_REGEX,),
            )
            used_codes = cur.fetchone()[0]
    finally:
        conn.close()

    if used_codes == 0:
        pytest.skip("No aligned standard codes in dim_question_data — empty warehouse.")

    assert dropped == [], (
        f"{len(dropped)} standard code(s) used by assessments have NO exact "
        f"dim_standard.schoology_standard match — a standards refresh likely "
        f"DROPPED their Schoology course-prefix alias rows. The per-item "
        f"rollups for these will silently collapse into the 'Other' bucket. "
        f"Missing aliases: {dropped}. "
        f"Restore them before reloading (see refresh_standards.py --full-pull "
        f"warning and docs/standards-alignment.md)."
    )
