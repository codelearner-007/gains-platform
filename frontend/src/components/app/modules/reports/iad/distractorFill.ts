import {
  INCORRECT_GREY,
  PERF_GREEN,
  PERF_PINK,
  PERF_YELLOW,
} from '@/lib/reports/colors';
import type { IadDistractorRow } from '@/lib/reports/types';

// Dominance thresholds (relative to the largest wrong-answer share). Match
// PBIX visuals #3 and #14 — the "most-picked wrong" gets pink, secondary
// gets yellow, the long tail goes neutral grey.
const DOMINANT_WRONG_THRESHOLD = 0.66;
const SECONDARY_WRONG_THRESHOLD = 0.33;

/**
 * Maximum share-of-attempts among the wrong-answer rows. Used to scale the
 * pink/yellow/grey gradient on each row's fill.
 */
export function maxIncorrectShareOf(rows: IadDistractorRow[]): number {
  return rows
    .filter((r) => !r.is_correct)
    .reduce((m, r) => Math.max(m, r.share_of_attempts), 0);
}

/**
 * Pick the traffic-light fill for one distractor row, given the
 * pre-computed maximum incorrect share for the question.
 *
 *   correct                      → PERF_GREEN
 *   wrong, no other wrongs       → INCORRECT_GREY
 *   wrong, share ≥ 66% of max    → PERF_PINK   (the dominant wrong choice)
 *   wrong, share ≥ 33% of max    → PERF_YELLOW (a secondary wrong choice)
 *   wrong, share <  33% of max   → INCORRECT_GREY (long-tail wrongs)
 */
export function distractorFill(
  row: IadDistractorRow,
  maxIncorrectShare: number,
): string {
  if (row.is_correct) return PERF_GREEN;
  if (maxIncorrectShare <= 0) return INCORRECT_GREY;
  const ratio = row.share_of_attempts / maxIncorrectShare;
  if (ratio >= DOMINANT_WRONG_THRESHOLD) return PERF_PINK;
  if (ratio >= SECONDARY_WRONG_THRESHOLD) return PERF_YELLOW;
  return INCORRECT_GREY;
}
