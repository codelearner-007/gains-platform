"""Parse a relative scraper blob path → (session, assessment_type, subject, grade, section, file_name).

Mirrors notebook lines 218-227 (data/_pbix_extract/40_schoology_py_spec.md §3 lines 175-188).

Given an input path RELATIVE to the school root (e.g. starting with `2025-26/...`):

    parts = ('2025-26', '1 - Lesson  Assessments', 'Mathematics', 'Grade 5', 'Sec 1', 'Question-Data-...csv')

We extract:
    session         = parts[0]
    assessment_type = parts[1] with the leading "<digit> - " prefix stripped (line 219)
                      e.g. "1 - Lesson  Assessments" -> "Lesson  Assessments" (note: TWO spaces preserved)
    subject         = parts[2].strip()
    grade           = parts[3].strip()
    section         = parts[4].strip()
    file_name       = parts[5]

Section names may be non-numeric (e.g. "Sec 1st Grade Team"); we do not validate.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePath


@dataclass(frozen=True)
class ParsedPath:
    """Result of parsing a relative scraper path."""

    session: str
    assessment_type: str
    subject: str
    grade: str
    section: str
    file_name: str

    @property
    def file_type(self) -> str:
        """Map file_name prefix to one of: question_data, submission_summary, student_submissions."""
        return classify_file_type(self.file_name)


class PathParseError(ValueError):
    """Raised when a path cannot be parsed into at least the 5-part shape."""


def _normalize(path: str | PurePath) -> tuple[str, ...]:
    """Convert any path-like to a tuple of POSIX-style parts."""
    if isinstance(path, PurePath):
        # Use parts then strip drive/anchor noise
        parts = path.parts
    else:
        # Treat as a string — split on both separators, drop empties.
        # Use PurePosixPath for forward-slashes; fall back manually for backslashes.
        s = str(path).replace("\\", "/")
        parts = tuple(p for p in s.split("/") if p)
    return parts


def parse_relative_path(rel_path: str | PurePath) -> ParsedPath:
    """Parse a relative scraper path → ParsedPath.

    The canonical layout is 6 components:
        session / assessment_type / subject / grade / section / file_name

    The legacy backup tree also contains two REAL structural variants that must
    not be silently dropped (they carry genuine, otherwise-missing assessments):

      * **7+ parts** — an extra subject-category folder is interposed, e.g.
        ``2025-26/Summative/Science/3 - Science/1 - Grade 1/Sec 01 SCI - C/file``
        (seen for some schools' Summative exports — e.g. Crestwell). The
        canonical subject/grade/section still sit at the DEEPEST levels, so we
        anchor subject/grade/section/file_name to the END and keep
        session/assessment_type at the front, absorbing any extra category
        folder(s) in between. For a canonical 6-part path this is byte-identical
        to the historical parse — regression-safe (Athenian baseline unchanged).

      * **5 parts** — a file placed directly under the grade folder with no
        section subfolder; ``section`` is left empty.

    Raises PathParseError for fewer than 5 parts.
    """
    parts = _normalize(rel_path)
    if len(parts) < 5:
        raise PathParseError(
            f"expected at least 5 path parts "
            f"(session/assessment_type/subject/grade[/section]/file_name), "
            f"got {len(parts)}: {parts!r}"
        )

    session = parts[0]
    assessment_type = _strip_assessment_prefix(parts[1])
    file_name = parts[-1]
    if len(parts) >= 6:
        # …/subject/grade/section/file_name — end-anchored so an interposed
        # subject-category folder (the 7-part variant) is absorbed harmlessly.
        section = parts[-2].strip()
        grade = parts[-3].strip()
        subject = parts[-4].strip()
    else:  # exactly 5 — no section subfolder
        section = ""
        grade = parts[-2].strip()
        subject = parts[-3].strip()

    return ParsedPath(
        session=session,
        assessment_type=assessment_type,
        subject=subject,
        grade=grade,
        section=section,
        file_name=file_name,
    )


def _strip_assessment_prefix(raw: str) -> str:
    """Implement notebook line 219: if value contains '-', take everything AFTER the FIRST '-'.

    Examples:
        "1 - Lesson  Assessments" -> "Lesson  Assessments"  (note: two spaces preserved!)
        "Module-Tests"            -> "Tests"
        "Pop Quiz"                -> "Pop Quiz"             (no dash, just trim)

    The double-space inside "1 - Lesson  Assessments" is intentional and must be preserved
    (this matches the literal Azure Blob folder name for Athenian).
    """
    if "-" in raw:
        # split once, take the part after the first '-', then strip
        _, _, rest = raw.partition("-")
        return rest.strip()
    return raw.strip()


def classify_file_type(file_name: str) -> str:
    """Map a CSV filename to its file_type identifier.

    Notebook line 489+. Filenames begin with a stable prefix:

        Question-Data-*           -> question_data
        Submission-Summary-*      -> submission_summary
        Student-Submissions-*     -> student_submissions

    Raises PathParseError for unknown prefixes.
    """
    if file_name.startswith("Question-Data"):
        return "question_data"
    if file_name.startswith("Submission-Summary"):
        return "submission_summary"
    if file_name.startswith("Student-Submissions"):
        return "student_submissions"
    raise PathParseError(f"unknown CSV file_type for filename: {file_name!r}")


def make_relative(blob_path: str | PurePath, root: str | PurePath) -> tuple[str, ...]:
    """Compute the parts of `blob_path` relative to `root`.

    Both arguments are path-like; we normalize to POSIX-style and compare.
    Returns the relative parts as a tuple.
    """
    blob_parts = _normalize(blob_path)
    root_parts = _normalize(root)

    # The root must be a prefix of blob_path
    if blob_parts[: len(root_parts)] != root_parts:
        raise PathParseError(f"blob path {blob_path!r} is not under root {root!r}")

    return blob_parts[len(root_parts) :]
