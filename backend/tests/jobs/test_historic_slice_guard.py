"""Proof tests for the §HISTORIC invariant (app/transformations/runner.py).

THE RULE
--------
A ``(school_id, session)`` slice of ``fact_student_submission`` that the raw layer
cannot rebuild must come out of a transform run byte-identical, or the entire run
raises and the caller's transaction rolls back.

WHY IT IS NOT A FLAG
--------------------
This replaced an ``ENVIRONMENT == "production"`` check plus an
``INGESTION_ALLOW_PROD_TRANSFORMS`` override. Both protected a *label*, not the
data: an ENVIRONMENT that was unset, misspelled, or copied from a dev template
onto a serving box disarmed the guard silently, and the failure it guards against
(every report erased) is unrecoverable. There is now nothing to configure and no
way to switch it off short of editing the runner — which is reviewable.

The tests below therefore assert BEHAVIOUR OF THE DATA CHECK, never an env value.
They are pure-logic and DB-free: the fingerprint/coverage queries are exercised
against the live DB by the report suite, while the decision function is unit-tested
here across every shape it must classify.
"""

from __future__ import annotations

import pytest

from app.transformations.runner import _assert_historic_slices_intact

# (school_id, session) -> (row_count, fingerprint)
ATH_2024 = ("school-a", "2024-25")
ATH_2025 = ("school-a", "2025-26")
CFP_2025 = ("school-b", "2025-26")


# ── The catastrophe this exists to stop ────────────────────────────────────


def test_wiping_a_slice_with_no_raw_ancestry_raises() -> None:
    """The production shape: fact is populated, raw is empty, a rebuild TRUNCATEs.

    With raw covering nothing, every slice is frozen, so the rebuild must be
    refused rather than repopulating the warehouse from nothing.
    """
    before = {ATH_2024: (572815, 111), ATH_2025: (656434, 222)}
    after: dict = {}                     # TRUNCATE + rebuild from an empty raw layer
    with pytest.raises(RuntimeError) as exc:
        _assert_historic_slices_intact(before, after, raw_coverage=set())

    msg = str(exc.value)
    assert "ROLLED BACK" in msg
    assert "2 historic" in msg
    # Both slices must be named — an operator needs to know what was at risk.
    assert "2024-25" in msg and "2025-26" in msg
    # And it must state plainly that there is no way around it.
    assert "no flag to bypass" in msg


def test_partial_collapse_raises_too_not_only_a_total_wipe() -> None:
    """The case the pre-existing collapse-guard misses.

    That guard only trips on fact >0 -> exactly 0. A rebuild that leaves a few
    hundred rows behind passes it, which is why this check compares per-slice.
    """
    before = {ATH_2024: (572815, 111), ATH_2025: (656434, 222)}
    after = {ATH_2025: (500, 999)}       # 2024-25 gone, 2025-26 gutted
    with pytest.raises(RuntimeError, match="ROLLED BACK"):
        _assert_historic_slices_intact(before, after, raw_coverage=set())


def test_a_frozen_slice_may_not_even_be_rewritten_identically_in_count() -> None:
    """Same row count, different content, is still a violation.

    Row counts alone would miss a rebuild that replaced historic rows with
    different ones — so the fingerprint is part of the comparison.
    """
    before = {ATH_2024: (572815, 111)}
    after = {ATH_2024: (572815, 999)}    # count identical, contents changed
    with pytest.raises(RuntimeError) as exc:
        _assert_historic_slices_intact(before, after, raw_coverage=set())
    assert "fingerprint CHANGED" in str(exc.value)


def test_a_frozen_slice_may_not_grow_either() -> None:
    """"Untouched" means untouched. Growth in a slice with no source is not a
    benign surprise — it means rows appeared from somewhere unaccounted for."""
    before = {ATH_2024: (100, 111)}
    after = {ATH_2024: (120, 333)}
    with pytest.raises(RuntimeError, match="ROLLED BACK"):
        _assert_historic_slices_intact(before, after, raw_coverage=set())


# ── It must not block the legitimate rebuild machine ───────────────────────


def test_identical_rebuild_passes() -> None:
    """The full-raw machine's normal case: everything reproduced exactly."""
    before = {ATH_2024: (572815, 111), ATH_2025: (656434, 222)}
    _assert_historic_slices_intact(before, dict(before), raw_coverage=set(before))


def test_a_reproducible_slice_may_change(caplog) -> None:
    """A slice raw CAN rebuild is allowed to change — the latest-export prune
    legitimately shrinks the session being re-ingested — but never silently."""
    before = {ATH_2025: (656434, 222)}
    after = {ATH_2025: (656400, 555)}    # pruned stale re-export rows
    with caplog.at_level("WARNING"):
        _assert_historic_slices_intact(before, after, raw_coverage={ATH_2025})
    assert any("IS rebuildable from raw" in r.message for r in caplog.records)


def test_a_new_year_can_be_added_while_prior_years_stay_frozen() -> None:
    """The scenario the owner actually asked about: ingesting a new year must not
    be able to damage the years already there."""
    before = {ATH_2024: (572815, 111), ATH_2025: (656434, 222)}
    after = {
        ATH_2024: (572815, 111),         # untouched
        ATH_2025: (656434, 222),         # untouched
        ("school-a", "2026-27"): (1234, 777),   # the new year
    }
    # Only the new year has raw; the prior two are frozen and unchanged.
    _assert_historic_slices_intact(
        before, after, raw_coverage={("school-a", "2026-27")}
    )


def test_mixed_run_reports_only_the_frozen_violations() -> None:
    """A reproducible slice changing must not be reported as a violation, and a
    frozen one changing must not be excused by its neighbour."""
    before = {ATH_2024: (100, 1), ATH_2025: (200, 2), CFP_2025: (300, 3)}
    after = {ATH_2024: (0, 0), ATH_2025: (150, 9), CFP_2025: (300, 3)}
    with pytest.raises(RuntimeError) as exc:
        _assert_historic_slices_intact(
            before, after, raw_coverage={ATH_2025},   # only 2025-26 is rebuildable
        )
    msg = str(exc.value)
    assert "1 historic" in msg, "only the frozen, changed slice counts"
    assert "school-a session=2024-25" in msg
    assert "school-b" not in msg, "an unchanged slice is not a violation"


def test_an_empty_database_is_not_a_violation() -> None:
    """A first-ever build has nothing to protect."""
    _assert_historic_slices_intact({}, {ATH_2025: (10, 1)}, raw_coverage=set())


# ── The removed configuration must stay removed ────────────────────────────


def test_no_env_var_can_disable_the_invariant() -> None:
    """The guarantee must not be re-attachable to configuration by accident.

    ``_assert_historic_slices_intact`` takes only data. If a future edit
    reintroduces a settings lookup inside it, this test is the tripwire.
    """
    import inspect

    from app.core.config import Settings

    src = inspect.getsource(_assert_historic_slices_intact)
    assert "settings" not in src, "the invariant must not consult configuration"
    assert "ENVIRONMENT" not in src
    # And the old escape hatch must be gone from the settings surface entirely.
    assert not hasattr(Settings, "INGESTION_ALLOW_PROD_TRANSFORMS")
    assert "INGESTION_ALLOW_PROD_TRANSFORMS" not in Settings.model_fields
