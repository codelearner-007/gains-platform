"""Phase 2/3 SQL transformation orchestrator.

Plain SQL files + Python orchestrator (no dbt — D4 in
`tasks/backlog/01-gains-pipeline-finalized-plan.md`). Each `.sql` file is a
1:1 port of one notebook step from
`data/_pbix_extract/40_schoology_py_spec.md` (the line-numbered ground truth).

Phase 2 ships staging + dimensions. Phase 3 will append fact/cube/hash entries
to TRANSFORMATIONS_ORDER.
"""

from .runner import TRANSFORMATIONS_ORDER, run_all

__all__ = ["TRANSFORMATIONS_ORDER", "run_all"]
