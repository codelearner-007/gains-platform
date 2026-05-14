"""CSV parsers — one per Schoology export file_type.

Each parser is a pure function: takes raw CSV bytes (+ context) and returns
a list of typed Pydantic models ready to INSERT into the matching raw_* table.

No DB access here — that lives in `app.jobs.ingest_schoology` and `app.jobs.db`.
"""
