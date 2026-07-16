"""Shared numeric constants.

Single source of truth for the PBIX-mandated performance band thresholds. These
were previously triplicated across ``report_service``, ``report_export_service``
and ``student_service`` (the last one percent-scaled), which risked the three
copies drifting apart. Keep the two scales explicit — callers that compare a
0–1 fraction use the fraction form; callers that compare a 0–100 percentage use
the ``_PCT`` form.

Parity notes:
- These mirror the web palette breakpoints in
  ``frontend/src/lib/reports/colors.ts`` (PERF_PINK <70, PERF_YELLOW 70–80,
  PERF_GREEN ≥80).
- The QSR paginated XLSX export uses a *local* yellow override (#FFF492) that is
  intentionally different from colors.ts (#FFF591) for exact legacy-SSRS .xlsx
  parity — that is a colour, not a threshold, and lives in
  ``report_export_service`` (``QSR_YELLOW_XLSX``); do not "reconcile" it here.
"""

from __future__ import annotations

# Band thresholds as 0–1 fractions: "at target" ≥ HIGH, "approaching" ≥ MID,
# "needs attention" below MID.
PERF_BAND_HIGH: float = 0.8
PERF_BAND_MID: float = 0.7

# Same thresholds as 0–100 percentages (for call sites that band a percentage).
PERF_BAND_HIGH_PCT: float = 80.0
PERF_BAND_MID_PCT: float = 70.0
