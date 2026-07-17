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

# ── Role hierarchy ranks (LOWER = more senior) ───────────────────────────────
# The role hierarchy is an ordinal rank where a SMALLER number means MORE
# authority. `super_admin` is always rank 0; custom roles occupy the contiguous
# band 1..N (1 = most senior custom); `user` sits at a fixed sentinel below all
# customs. A user's *effective rank* = MIN(rank) over their roles. The rule
# everywhere: an actor may manage a target only when the target's rank is
# STRICTLY GREATER (more junior). No numbers are ever shown in the UI.
SUPER_ADMIN_RANK: int = 0            # pinned system role — most senior
USER_ROLE_RANK: int = 100_000       # pinned system role — always junior to customs
NO_ROLE_RANK: int = 2_147_483_647   # sentinel: no roles / missing claim = most junior (fail-closed)
MAX_CUSTOM_ROLES: int = 500         # keeps custom ranks (1..N) well below USER_ROLE_RANK
