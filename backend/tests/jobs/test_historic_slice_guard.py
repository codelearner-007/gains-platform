"""Proof tests for the §HISTORIC invariant (app/transformations/runner.py).

THE RULE
--------
A ``(school_id, session, subject_id)`` slice of ``fact_student_submission`` whose
subject is NOT part of the run's declared scope must come out of a transform run
byte-identical, or the entire run raises and the caller's transaction rolls back.

WHAT "IN SCOPE" MEANS
---------------------
``_assert_historic_slices_intact(before, after, in_scope)`` is keyed on
``(school_id, session, subject_id)`` and takes ``in_scope`` — a frozenset of the
subject_ids this run is allowed to rewrite:

  * Full rebuild: ``in_scope`` = every subject_id present in the FRESHLY-BUILT
    fact. A subject the rebuild reproduces is exempt; a subject a staging/fact bug
    silently DROPPED is absent from the fresh fact ⇒ not in scope ⇒ its vanished
    rows RAISE.
  * Scoped rebuild: ``in_scope`` = the roster-gate SURVIVORS. Everything else
    (pruned / rename-swept-then-pruned / purely historic) must be byte-identical.
    On prod (empty raw) ``in_scope`` is empty ⇒ every historic subject is frozen.

WHY IT IS NOT A FLAG
--------------------
This replaced an ``ENVIRONMENT == "production"`` check plus an
``INGESTION_ALLOW_PROD_TRANSFORMS`` override. Both protected a *label*, not the
data: an ENVIRONMENT that was unset, misspelled, or copied from a dev template
onto a serving box disarmed the guard silently, and the failure it guards against
(every report erased) is unrecoverable. There is now nothing to configure and no
way to switch it off short of editing the runner — which is reviewable.

The tests below therefore assert BEHAVIOUR OF THE DATA CHECK, never an env value.
They are pure-logic and DB-free: the fingerprint queries are exercised against the
live DB by the report suite, while the decision function is unit-tested here
across every shape it must classify.
"""

from __future__ import annotations

import pytest

from app.transformations.runner import _assert_historic_slices_intact

# (school_id, session, subject_id) -> (row_count, fingerprint)
ATH_2024 = ("school-a", "2024-25", "subj-a24")
ATH_2025 = ("school-a", "2025-26", "subj-a25")
CFP_2025 = ("school-b", "2025-26", "subj-b25")


# ── The catastrophe this exists to stop ────────────────────────────────────


def test_wiping_a_slice_with_no_raw_ancestry_raises() -> None:
    """The production shape: fact is populated, the run declares NO scope, a
    rebuild wipes everything.

    With ``in_scope`` empty every subject is frozen, so the rebuild must be
    refused rather than repopulating the warehouse from nothing.
    """
    before = {ATH_2024: (572815, 111), ATH_2025: (656434, 222)}
    after: dict = {}                     # TRUNCATE + rebuild from an empty raw layer
    with pytest.raises(RuntimeError) as exc:
        _assert_historic_slices_intact(before, after, in_scope=frozenset())

    msg = str(exc.value)
    assert "ROLLED BACK" in msg
    assert "2 (school, session, subject)" in msg
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
        _assert_historic_slices_intact(before, after, in_scope=frozenset())


def test_a_frozen_slice_may_not_even_be_rewritten_identically_in_count() -> None:
    """Same row count, different content, is still a violation.

    Row counts alone would miss a rebuild that replaced historic rows with
    different ones — so the fingerprint is part of the comparison.
    """
    before = {ATH_2024: (572815, 111)}
    after = {ATH_2024: (572815, 999)}    # count identical, contents changed
    with pytest.raises(RuntimeError) as exc:
        _assert_historic_slices_intact(before, after, in_scope=frozenset())
    assert "fingerprint CHANGED" in str(exc.value)


def test_a_frozen_slice_may_not_grow_either() -> None:
    """"Untouched" means untouched. Growth in a slice outside the run's scope is
    not a benign surprise — it means rows appeared from somewhere unaccounted
    for."""
    before = {ATH_2024: (100, 111)}
    after = {ATH_2024: (120, 333)}
    with pytest.raises(RuntimeError, match="ROLLED BACK"):
        _assert_historic_slices_intact(before, after, in_scope=frozenset())


def test_covered_slice_collapse_with_empty_scope_raises() -> None:
    """Defect-fix regression (the reason this signature exists).

    A big in-warehouse slice that collapses to a handful of rows must RAISE even
    though a total-wipe guard (fact >0 -> exactly 0) would sail right past it,
    whenever the run declares NO scope (prod's empty-scope freeze). The old
    ``(school, session)`` + ``raw_coverage`` signature could not express this: a
    slice whose (school, session) had *some* raw was treated as rebuildable and
    its collapse was excused. Keyed per-subject with ``in_scope`` empty, the
    collapse is a violation.
    """
    big = ("school-a", "2025-26", "subj-a25")
    before = {big: (656434, 424242)}
    after = {big: (20, 5)}               # ~20 rows left behind — the silent collapse
    with pytest.raises(RuntimeError, match="ROLLED BACK"):
        _assert_historic_slices_intact(before, after, in_scope=frozenset())


# ── It must not block the legitimate rebuild machine ───────────────────────


def test_identical_rebuild_passes() -> None:
    """The full-raw machine's normal case: everything reproduced exactly.

    ``in_scope`` = every freshly-built subject; the before/after fingerprints are
    identical so nothing even needs the exemption.
    """
    before = {ATH_2024: (572815, 111), ATH_2025: (656434, 222)}
    in_scope = frozenset({ATH_2024[2], ATH_2025[2]})
    _assert_historic_slices_intact(before, dict(before), in_scope=in_scope)


def test_a_reproducible_slice_may_change(caplog) -> None:
    """A subject INSIDE the run's scope is allowed to change — the latest-export
    prune legitimately shrinks the session being re-ingested — but never
    silently."""
    before = {ATH_2025: (656434, 222)}
    after = {ATH_2025: (656400, 555)}    # pruned stale re-export rows
    with caplog.at_level("WARNING"):
        _assert_historic_slices_intact(
            before, after, in_scope=frozenset({ATH_2025[2]})
        )
    assert "in-scope slice changed" in caplog.text


def test_a_new_year_can_be_added_while_prior_years_stay_frozen() -> None:
    """The scenario the owner actually asked about: ingesting a new year must not
    be able to damage the years already there."""
    before = {ATH_2024: (572815, 111), ATH_2025: (656434, 222)}
    new_year = ("school-a", "2026-27", "subj-a2627")
    after = {
        ATH_2024: (572815, 111),         # untouched
        ATH_2025: (656434, 222),         # untouched
        new_year: (1234, 777),           # the new year (only subject in scope)
    }
    _assert_historic_slices_intact(before, after, in_scope=frozenset({new_year[2]}))


def test_mixed_run_reports_only_the_out_of_scope_violations() -> None:
    """An in-scope subject changing must not be reported as a violation, and an
    out-of-scope one changing must not be excused by its neighbour."""
    before = {ATH_2024: (100, 1), ATH_2025: (200, 2), CFP_2025: (300, 3)}
    after = {ATH_2024: (0, 0), ATH_2025: (150, 9), CFP_2025: (300, 3)}
    with pytest.raises(RuntimeError) as exc:
        _assert_historic_slices_intact(
            before, after, in_scope=frozenset({ATH_2025[2]}),  # only subj-a25 in scope
        )
    msg = str(exc.value)
    assert "1 (school, session, subject)" in msg, "only the frozen, changed slice counts"
    assert "school-a session=2024-25" in msg
    assert "school-b" not in msg, "an unchanged slice is not a violation"


def test_an_empty_database_is_not_a_violation() -> None:
    """A first-ever build has nothing to protect."""
    _assert_historic_slices_intact({}, {ATH_2025: (10, 1)}, in_scope=frozenset())


# ── (f) #15 FULL-MODE-ONLY relabel downgrade ────────────────────────────────
# A full rebuild on the local machine that applies an override seed (e.g. the
# GAI-13 Crestwell ELA->Reading relabel) MOVES every row of an assessment from
# OLD_subject_id to NEW_subject_id inside one (school, session). The freshly-built
# fact contains NEW but not OLD, so OLD looks "dropped" to the per-subject guard.
# ``full_mode_raw_coverage`` downgrades that to a logged relabel IFF the slice's
# (school, session) is raw-covered AND its slice-level (Σcount, Σfingerprint) is
# preserved (rows moved, none lost). A genuine shrink still RAISES. Scoped mode
# passes ``None`` and stays strict (prod fail-closed).


def test_full_mode_relabel_within_covered_slice_is_permitted(caplog) -> None:
    """The override-seed workflow: OLD_subject_id → NEW_subject_id, same rows, same
    (school, session) which the raw layer can rebuild. The slice-level count +
    fingerprint are preserved, so the out-of-scope OLD subject's 100 -> 0 change is
    a logged relabel, not a rollback."""
    old = ("school-a", "2024-25", "subj-OLD")
    new = ("school-a", "2024-25", "subj-NEW")
    before = {old: (100, 5)}
    after = {new: (100, 5)}  # rows moved OLD->NEW; slice (Σcount,Σfp) preserved
    with caplog.at_level("WARNING"):
        _assert_historic_slices_intact(
            before, after,
            in_scope=frozenset({new[2]}),           # fresh-fact subjects = NEW only
            full_mode_raw_coverage={("school-a", "2024-25")},
        )
    assert "relabel" in caplog.text


def test_full_mode_genuine_slice_shrink_still_raises() -> None:
    """A real DROP (rows lost, not moved) shrinks the slice-level total even in a
    raw-covered slice → still a violation, even in full mode."""
    old = ("school-a", "2024-25", "subj-OLD")
    before = {old: (100, 5)}
    after: dict = {}  # the assessment's rows vanished — nothing replaces them
    with pytest.raises(RuntimeError, match="ROLLED BACK"):
        _assert_historic_slices_intact(
            before, after,
            in_scope=frozenset(),
            full_mode_raw_coverage={("school-a", "2024-25")},
        )


def test_full_mode_relabel_in_uncovered_slice_still_raises() -> None:
    """Condition (i): the downgrade applies ONLY to raw-covered slices. The SAME
    slice-preserving relabel in a (school, session) the raw layer CANNOT rebuild
    (prod / a true archived drop) still RAISES."""
    old = ("school-a", "2024-25", "subj-OLD")
    new = ("school-a", "2024-25", "subj-NEW")
    before = {old: (100, 5)}
    after = {new: (100, 5)}
    with pytest.raises(RuntimeError, match="ROLLED BACK"):
        _assert_historic_slices_intact(
            before, after,
            in_scope=frozenset({new[2]}),
            full_mode_raw_coverage=set(),           # (school-a,2024-25) NOT covered
        )


def test_scoped_mode_relabel_stays_fail_closed() -> None:
    """Scoped mode passes ``full_mode_raw_coverage=None`` → NO downgrade. The very
    relabel that a full rebuild permits still RAISES under a scoped run, keeping
    prod fail-closed."""
    old = ("school-a", "2024-25", "subj-OLD")
    new = ("school-a", "2024-25", "subj-NEW")
    before = {old: (100, 5)}
    after = {new: (100, 5)}
    with pytest.raises(RuntimeError, match="ROLLED BACK"):
        _assert_historic_slices_intact(
            before, after, in_scope=frozenset({new[2]})  # scoped: coverage=None
        )


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
