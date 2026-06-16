import { describe, expect, it } from 'vitest';
import {
  QSR_GREEN,
  QSR_PINK,
  QSR_POINTS_GREY,
  qsrPerformanceColor,
} from '../lib/reports/colors';

/**
 * The Question Summary Report bands the Student Name and Score % cells by the
 * student's score, using the EXACT legacy SSRS traffic-light hexes and the
 * legacy `Round(score, 2)` before the threshold compare. These are verbatim
 * from the rendered legacy PDFs:
 *   <70%   → pink   #FFCCFF
 *   70–80% → yellow #fff492
 *   ≥80%   → green  #99FF99
 * and the Possible Points / # Correct Answers cells are grey #D3D3D3.
 * Regression guard: a drift here silently mis-colors every QSR.
 */
describe('qsrPerformanceColor — legacy QSR bands', () => {
  it('colors <70% pink', () => {
    expect(qsrPerformanceColor(0)).toBe(QSR_PINK);
    expect(qsrPerformanceColor(0.45)).toBe(QSR_PINK);
    expect(qsrPerformanceColor(0.69)).toBe(QSR_PINK);
  });

  it('colors 70–80% yellow', () => {
    expect(qsrPerformanceColor(0.7)).toBe('#fff492');
    expect(qsrPerformanceColor(0.77)).toBe('#fff492');
    expect(qsrPerformanceColor(0.79)).toBe('#fff492');
  });

  it('colors ≥80% green', () => {
    expect(qsrPerformanceColor(0.8)).toBe(QSR_GREEN);
    expect(qsrPerformanceColor(0.82)).toBe(QSR_GREEN);
    expect(qsrPerformanceColor(1)).toBe(QSR_GREEN);
  });

  it('applies legacy Round(score, 2) at the band boundary', () => {
    // 0.795 rounds to 0.80 → green (matches the legacy RDL IIf rounding);
    // 0.794 rounds to 0.79 → yellow.
    expect(qsrPerformanceColor(0.795)).toBe(QSR_GREEN);
    expect(qsrPerformanceColor(0.794)).toBe('#fff492');
    // 0.695 rounds to 0.70 → yellow (no longer pink).
    expect(qsrPerformanceColor(0.695)).toBe('#fff492');
  });

  it('pins the exact legacy hexes (drift guard)', () => {
    expect(QSR_PINK).toBe('#FFCCFF');
    expect(QSR_GREEN).toBe('#99FF99');
    expect(QSR_POINTS_GREY).toBe('#D3D3D3');
  });
});
