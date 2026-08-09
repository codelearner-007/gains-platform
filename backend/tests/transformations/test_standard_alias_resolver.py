"""Pin the standard-alias resolver: importability, resolution semantics, and the
single-source-of-truth wiring between the backend module and the seed.

Regression context: the resolver logic used to live only in
``supabase/seeds/augment_standard_aliases.py`` and the transform runner imported
it by injecting ``../supabase/seeds`` onto ``sys.path`` at call time. That path
does not exist in the backend Docker image (build context = ``backend/`` only),
so every transform that reached the alias step raised ``ModuleNotFoundError`` and
rolled back. The fix moved the pure logic into
``app.transformations.standard_alias_resolver`` (shipped in the image); the seed
now loads that same file by path. These tests fail on the pre-fix tree and pin
the fix so the bug class cannot return.

DB-free: requests no fixtures, opens no connection.
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

from app.transformations import standard_alias_resolver as backend_mod
from app.transformations.standard_alias_resolver import (
    AliasResolver,
    _CODE_SHAPE,
    _COPY_COLS,
    _cpalms_from_alias,
    _drop_leaf,
)

_REPO_ROOT = Path(__file__).resolve().parents[3]
_BACKEND_MODULE = _REPO_ROOT / "backend" / "app" / "transformations" / "standard_alias_resolver.py"
_SEED = _REPO_ROOT / "supabase" / "seeds" / "augment_standard_aliases.py"

# Frozen literal — the cube-join / alias-coverage code-shape predicate. If this
# ever needs to change, change it deliberately (both consumers read this object).
_CODE_SHAPE_LITERAL = r"\.[^.]*[0-9]|[0-9][^.]*\."

# Curated base-code universe covering both resolution passes.
_CODES = ["SC.3.N.1.1", "SS.912.W.1.6", "SC.2.P.13.1", "LAFS.5.L.1.1", "MA.912.AR.3.1"]


def _resolver() -> AliasResolver:
    return AliasResolver(_CODES, {c: "subj" for c in _CODES})


def _load_seed_module():
    """Load the seed the way its CLI does (by file path). Import-safe: the seed
    connects to no DB at import time (psycopg2.connect lives in main())."""
    spec = importlib.util.spec_from_file_location("augment_standard_aliases_under_test", _SEED)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ── t1: importability + symbol surface ──────────────────────────────────────
def test_backend_module_exposes_all_symbols():
    assert isinstance(_CODE_SHAPE, re.Pattern)
    assert isinstance(backend_mod._COURSE_PREFIX, re.Pattern)
    assert isinstance(backend_mod._GRADE_TOKEN, re.Pattern)
    assert isinstance(_COPY_COLS, tuple) and len(_COPY_COLS) == 13
    assert _COPY_COLS[0] == "identifier" and _COPY_COLS[-1] == "rundate"
    assert callable(_drop_leaf) and callable(_cpalms_from_alias)
    assert isinstance(backend_mod.AliasResolver, type)


def test_code_shape_pattern_is_frozen():
    # The exact cube-join predicate; a silent change would corrupt rollups.
    assert _CODE_SHAPE.pattern == _CODE_SHAPE_LITERAL


# ── t2: resolution semantics (both passes, grade preference, unresolved) ─────
def test_resolve_substring_pass():
    r = _resolver()
    # Pass 1: longest base that is a substring of the alias.
    assert r.resolve("SCI.3.SC.3.N.1.1") == "SC.3.N.1.1"
    assert r.resolve("SOC.9-12.SS.912.W.1.6") == "SS.912.W.1.6"
    assert r.resolve("AI.MA.912.AR.3.1") == "MA.912.AR.3.1"


def test_resolve_prefix_strip_and_hierarchy_walk():
    r = _resolver()
    # Pass 2: no substring base exists → strip course prefix, walk up, prefer grade.
    assert r.resolve("SC.2.P.13.A") == "SC.2.P.13.1"
    assert r.resolve("ELA.5.L.1.1.d") == "LAFS.5.L.1.1"


def test_resolve_unresolved_returns_none():
    r = _resolver()
    # No base family in the universe → None (never invent a standard).
    assert r.resolve("ZZ.9.QQ.99.9.9") is None


def test_drop_leaf_and_cpalms():
    assert _drop_leaf("SC.3.N.1.1") == "SC.3.N.1"
    assert _drop_leaf("SC") == "SC"  # no dot → unchanged
    assert _cpalms_from_alias("AI.MA.912.AR.3.1") == "912.AR.3.1"
    assert _cpalms_from_alias("SCI.3.SC.3.N.1.1") == "SC.3.N.1.1"


# ── t3: single source of truth — the seed loads the backend file, and both
#        instances behave identically ─────────────────────────────────────────
def test_seed_loads_the_backend_resolver_file():
    seed = _load_seed_module()
    # The seed resolves to exactly the backend module file (one source of truth).
    assert seed._resolver_path.resolve() == _BACKEND_MODULE.resolve()


def test_seed_and_backend_resolver_behaviour_is_identical():
    seed = _load_seed_module()
    # Same source file, so patterns + column tuple must match exactly.
    assert seed._CODE_SHAPE.pattern == _CODE_SHAPE.pattern
    assert seed._COPY_COLS == _COPY_COLS
    # And resolution parity across the golden corpus (guards against a stale copy).
    aliases = [
        "SCI.3.SC.3.N.1.1",
        "SOC.9-12.SS.912.W.1.6",
        "AI.MA.912.AR.3.1",
        "SC.2.P.13.A",
        "ELA.5.L.1.1.d",
        "ZZ.9.QQ.99.9.9",
    ]
    subj = {c: "subj" for c in _CODES}
    seed_r = seed.AliasResolver(_CODES, subj)
    backend_r = AliasResolver(_CODES, subj)
    for a in aliases:
        assert seed_r.resolve(a) == backend_r.resolve(a), a


# ── t4: regression tripwire — the exact bug class cannot return ──────────────
def test_resolve_pass2_tiebreak_and_graded_empty_fallback():
    # A custom universe that exercises pass-2 branches the golden set doesn't:
    # the `_drop_leaf(c) == cand` (c3) and `_drop_leaf(c).endswith` (c4) match
    # conditions, the graded-EMPTY fallback (no candidate carries the alias's
    # grade, so the grade filter is skipped), and the `matches.sort(key=len)`
    # shortest-wins tie-break.
    codes = ["B.1.1", "A.B.1.1"]
    r = AliasResolver(codes, {c: "subj" for c in codes})
    # "XX.9.B.1.A": no substring base; strip "XX.9." → "B.1.A"; walk up to "B.1",
    # where both codes match (c3 / c4); grade "9" matches neither (fallback);
    # shorter "B.1.1" wins the tie.
    assert r.resolve("XX.9.B.1.A") == "B.1.1"


def test_resolve_no_course_prefix_branch():
    # Exercises the `_COURSE_PREFIX` non-match path (m is None → core = alias).
    r = _resolver()
    # "N.1.1": lookahead after "N.1." is a digit, so no course-prefix match;
    # walks to a base ending ".N.1.1".
    assert r.resolve("N.1.1") == "SC.3.N.1.1"


def test_runner_has_no_seeds_import_or_extra_syspath():
    # Regression tripwire for the exact prod bug: the runner used to inject
    # ``../supabase/seeds`` onto sys.path and import the resolver by bare name.
    src = (_REPO_ROOT / "backend" / "app" / "transformations" / "runner.py").read_text()
    assert "supabase" not in src, "runner.py must not reference supabase/"
    assert "from augment_standard_aliases import" not in src, (
        "runner must import the resolver from app.transformations.standard_alias_resolver"
    )
    # The ONLY permitted sys.path mutation is the top-of-file backend bootstrap;
    # no per-call injection of any other directory (insert OR append) may return.
    mutations = re.findall(r"_sys\.path\.(?:insert|append)\([^)]*\)", src)
    assert mutations == ["_sys.path.insert(0, _BACKEND_DIR)"], (
        f"unexpected sys.path mutation(s) in runner.py: {mutations}"
    )


def test_runner_imports_cleanly():
    # Module-level import must succeed with only the backend package present
    # (this is the import that failed in prod).
    import app.transformations.runner as runner  # noqa: F401

    assert runner._augment_standard_aliases is not None
