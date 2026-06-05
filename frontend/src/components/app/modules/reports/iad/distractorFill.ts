import { INCORRECT_GREY, PERF_GREEN } from '@/lib/reports/colors';
import type { IadDistractorRow } from '@/lib/reports/types';

// Legacy parity: the PBIX IAD "Answer Distribution" tableEx (#4) and the
// hidden treemap (#14) carry NO per-cell color rule (01_legacy_logic.md
// §4.3 / §4.6 — "a per-cell color rule was never written in DAX for this
// treemap"). The earlier traffic-light encoding (pink = dominant wrong,
// yellow = secondary wrong) was a non-legacy invention and has been
// removed (MASTER_PLAN §6 Decision 3). Distractor cells now render with a
// neutral grey fill; the saturated correct/incorrect colors live only on
// the per-student "Correct?" column where legacy uses them.

/**
 * Neutral fill for one distractor row. The correct answer keeps a soft
 * green so it remains visually distinguishable from the wrong choices;
 * every wrong choice renders neutral grey (no relative-share encoding).
 */
export function distractorFill(row: IadDistractorRow): string {
  return row.is_correct ? PERF_GREEN : INCORRECT_GREY;
}
