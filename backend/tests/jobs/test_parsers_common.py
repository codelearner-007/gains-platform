"""Tests for app.jobs.parsers.common — focused on the decode fallback chain.

~67% of the legacy backup's Student-Submissions CSVs are cp1252/latin-1, not
UTF-8. The reader must decode them (the legacy notebook read pre-landing as
ISO-8859-1) rather than raise UnicodeDecodeError and be silently skipped by the
ingest per-file SAVEPOINT.
"""

from __future__ import annotations

import logging

from app.jobs.parsers.common import decode_csv_bytes, read_csv_bytes


def test_utf8_sig_bom_is_decoded() -> None:
    """A BOM-prefixed UTF-8 file (the scraper's format) decodes cleanly, no fallback."""
    text = "User UID,First Name\n134618215,José\n"
    data = text.encode("utf-8-sig")
    assert decode_csv_bytes(data) == text


def test_cp1252_smart_punctuation_falls_back() -> None:
    """cp1252 bytes (0x92 right single quote, 0xa0 nbsp) are not valid utf-8-sig.

    Without the fallback these raise UnicodeDecodeError. The decoder must fall
    back and preserve the characters.
    """
    text = "Item Name,Question\nO’Brien Quiz,Find the value\n"
    data = text.encode("cp1252")
    decoded = decode_csv_bytes(data)
    assert "’" in decoded  # right single quotation mark
    assert " " in decoded  # non-breaking space (the 0xa0 byte)


def test_latin1_accented_name_falls_back() -> None:
    """ISO-8859-1 (latin-1) bytes with an accented name decode via the fallback chain."""
    text = "First Name,Last Name\nJosé,Muñoz\n"
    data = text.encode("latin-1")
    decoded = decode_csv_bytes(data)
    assert "José" in decoded
    assert "Muñoz" in decoded


def test_fallback_is_logged_not_silent(caplog) -> None:
    """A file that needs a fallback codec is LOGGED (the operator can spot-check),
    never silently dropped."""
    data = "First Name\nJosé\n".encode("latin-1")
    with caplog.at_level(logging.WARNING, logger="ingest_schoology.parsers"):
        decode_csv_bytes(data, source_name="Student-Submissions-Foo.csv")
    assert any(
        "Student-Submissions-Foo.csv" in r.message and "fallback" in r.message
        for r in caplog.records
    ), f"expected a fallback WARNING naming the file, got {[r.message for r in caplog.records]}"


def test_utf8_sig_decode_is_not_logged(caplog) -> None:
    """The happy path (valid utf-8-sig) emits no fallback warning."""
    data = "First Name\nAlice\n".encode("utf-8-sig")
    with caplog.at_level(logging.WARNING, logger="ingest_schoology.parsers"):
        decode_csv_bytes(data, source_name="Student-Submissions-Bar.csv")
    assert not any("fallback" in r.message for r in caplog.records)


def test_read_csv_bytes_parses_latin1_rows() -> None:
    """read_csv_bytes (the ingest entry point) parses a latin-1 file end-to-end."""
    data = "User UID,First Name,Last Name\n42,José,Muñoz\n".encode("latin-1")
    headers, rows = read_csv_bytes(data, source_name="Student-Submissions-Baz.csv")
    assert headers == ["User UID", "First Name", "Last Name"]
    assert rows == [{"User UID": "42", "First Name": "José", "Last Name": "Muñoz"}]
