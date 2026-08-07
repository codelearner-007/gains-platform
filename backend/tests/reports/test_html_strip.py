"""Standard-description HTML-strip suite — READ-ONLY.

Evan (2026-08-01) + Dan (2026-08-03) reported that some standard descriptions
render literal HTML (``<p>``, ``<li>`` …). The raw text lives in
``dim_standard.description`` (from the CASE/CFItem ``fullStatement``); the fix
strips it at the service boundary via the existing ``_strip_html`` helper. Four
serving paths were missing the wrap:
``assessment_service.get_questions`` / ``.get_standards``,
``reports.per_assessment`` (IAD question context) and
``student_service`` (per-student standard rows).

This suite pins:
  * ``_strip_html`` removes every observed tag, decodes entities, preserves
    ``<https://…>`` image placeholders, is idempotent and None-safe (unit); and
  * the QRA/Standards serving path (``AssessmentService.get_standards`` /
    ``.get_questions``) returns descriptions with NO residual tags/entities for
    a real Athenian assessment whose standards DO carry HTML in the raw data.

Same READ-ONLY, roll-back discipline as the rest of ``tests/reports``. Run:
    cd backend && ./venv/bin/python -m pytest tests/reports/test_html_strip.py -q
"""

from __future__ import annotations

import re

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.assessment_service import AssessmentService
from app.services.reports import _strip_html

ATHENIAN = "019eb11c-410a-7ffb-86e6-a0294c669670"
# Anchor: Athenian "HW 4/11 Chapter 8 Review" — 15 of its standards carry HTML
# in dim_standard.description (discovered 2026-08-06). The report key is the
# merged subject_id, exactly as the API passes it to get_standards.
ANCHOR_HTML_SUBJECT = (
    "dd54238e5655c3775eeb7a4a59db09fc091cb6e9ffeb8f63be6bfb142fa4630f"
)

_TAG_RE = re.compile(r"<[a-zA-Z/][^>]*>")
_ENTITY_RE = re.compile(r"&[a-zA-Z]+;|&#\d+;")


async def scope(session: AsyncSession, school_id: str) -> None:
    await session.execute(text("SET LOCAL ROLE authenticated"))
    await session.execute(
        text("SELECT set_config('app.current_school_id', :s, true)"),
        {"s": school_id},
    )


# ════════════════════════════════════════════════════════════════════════════
# 1. _strip_html unit behaviour (no DB)
# ════════════════════════════════════════════════════════════════════════════
class TestStripHtmlUnit:
    def test_removes_every_observed_tag(self):
        raw = (
            "<p>Understand</p><ol><li>count</li></ol>"
            "<strong>bold</strong> <b>b</b> <i>i</i> <em>e</em>"
            '<span class="x">s</span><div>d</div><br>'
            "<ul><li>x</li></ul>word problems<sup>1</sup>"
        )
        out = _strip_html(raw)
        assert not _TAG_RE.search(out), out
        # text content survives
        for token in ("Understand", "count", "bold", "word problems"):
            assert token in out

    def test_decodes_named_and_numeric_entities(self):
        assert _strip_html("&ldquo;more of&rdquo;") == "“more of”"
        assert _strip_html("a &mdash; b") == "a — b"
        assert _strip_html("Jack &amp; Jill") == "Jack & Jill"
        # after decode+strip, no entity syntax remains
        assert not _ENTITY_RE.search(_strip_html("&pi; &le; &ge;"))

    def test_entity_escaped_markup_is_neutralised_not_left_live(self):
        # "&lt;b&gt;x&lt;/b&gt;" decodes to "<b>x</b>" then strips to "x"
        assert _strip_html("&lt;b&gt;x&lt;/b&gt;") == "x"

    def test_preserves_image_url_placeholder(self):
        # the helper's negative lookahead keeps <https://…> for the image path
        s = "See <https://example.com/img.png> here"
        assert "<https://example.com/img.png>" in _strip_html(s)

    def test_idempotent_on_plain_text_and_none_safe(self):
        plain = "Solve addition and subtraction word problems."
        assert _strip_html(plain) == plain
        assert _strip_html(_strip_html(plain)) == plain
        assert _strip_html(None) == ""
        assert _strip_html("") == ""

    def test_preserves_math_inequalities(self):
        # Inequality operators must SURVIVE — only markup is removed. Regression
        # guard for the adversarial finding that the old strip deleted the
        # "x < a" clause on inequality standards.
        #
        # THE REAL dim_standard shape (id 3c472b67) is LITERAL tags with a
        # literal '<' operator between them — the old regex ate from the '<'
        # operator to the next tag's '>'. The tighter tag regex (letter after
        # '<') now preserves the operator:
        assert (
            _strip_html("<i>x </i>> <i>a</i>, <i>x </i>< <i>a</i>")
            == "x > a, x < a"
        )
        assert _strip_html("x < 5 and y > 2") == "x < 5 and y > 2"
        # Entity-escaped inputs are handled DEFENSIVELY (dim_standard has none
        # today, but the CASE/CFItem source is HTML): entity operators survive,
        # entity-escaped tags are removed.
        assert _strip_html("x &lt; 5 and y &gt; 2") == "x < 5 and y > 2"
        assert _strip_html("&lt;i&gt;x&lt;/i&gt; &lt; 5") == "x < 5"


# ════════════════════════════════════════════════════════════════════════════
# 2. Serving path — get_standards / get_questions return clean descriptions
# ════════════════════════════════════════════════════════════════════════════
class TestServingPathStripsHtml:
    async def _raw_html_std_count(self, db: AsyncSession, subject_id: str) -> int:
        return (
            await db.execute(
                text(
                    """
                    SELECT count(DISTINCT ds.identifier)
                    FROM dim_item di
                    JOIN cube_standard_summary cs ON cs.item_id = di.item_id
                    JOIN dim_standard ds ON ds.identifier = cs.identifier
                    WHERE di.subject_id = :sid
                      AND ds.description ~ '<[a-zA-Z/][^>]*>'
                    """
                ),
                {"sid": subject_id},
            )
        ).scalar()

    async def test_get_standards_descriptions_are_clean(self, db: AsyncSession):
        await scope(db, ATHENIAN)
        # meaningfulness guard: the raw data for this anchor DOES contain HTML,
        # so a clean serving result actually proves the strip is doing work.
        raw_html = await self._raw_html_std_count(db, ANCHOR_HTML_SUBJECT)
        assert raw_html > 0, "anchor no longer has HTML standards — pick a new one"

        rows = await AssessmentService(db).get_standards(ANCHOR_HTML_SUBJECT)
        described = [r.description for r in rows if r.description]
        assert described, "expected at least one standard with a description"
        for d in described:
            assert not _TAG_RE.search(d), f"residual tag in: {d!r}"
            assert not _ENTITY_RE.search(d), f"residual entity in: {d!r}"

    async def test_get_questions_descriptions_are_clean(self, db: AsyncSession):
        await scope(db, ATHENIAN)
        rows = await AssessmentService(db).get_questions(ANCHOR_HTML_SUBJECT)
        for r in rows:
            if r.description:
                assert not _TAG_RE.search(r.description), r.description
                assert not _ENTITY_RE.search(r.description), r.description
