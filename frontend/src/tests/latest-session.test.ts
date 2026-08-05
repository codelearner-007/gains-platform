import { describe, expect, it } from 'vitest';
import { latestSessionLabel } from '@/lib/reports/use-latest-session';
import type { SessionRow } from '@/lib/reports/types';

// `latestSessionLabel` is the pure resolver behind `useEffectiveSession`: given a
// `dim_session` list it returns the newest (lexical-max) non-null label, or
// `undefined` when there is nothing to resolve. The result must be
// order-independent so gated report pages always default to the latest session
// regardless of how the sessions query happens to be ordered.

function row(session: string | null, id = session ?? 'null'): SessionRow {
  return { session_id: `sid-${id}`, session };
}

describe('latestSessionLabel', () => {
  it('returns the newest label from an ascending list', () => {
    const rows = [row('2023-24'), row('2024-25'), row('2025-26')];
    expect(latestSessionLabel(rows)).toBe('2025-26');
  });

  it('is order-independent (descending and shuffled agree)', () => {
    const descending = [row('2025-26'), row('2024-25'), row('2023-24')];
    const shuffled = [row('2024-25'), row('2025-26'), row('2023-24')];
    expect(latestSessionLabel(descending)).toBe('2025-26');
    expect(latestSessionLabel(shuffled)).toBe('2025-26');
  });

  it('ignores null session labels', () => {
    const rows = [row(null, 'a'), row('2024-25'), row(null, 'b')];
    expect(latestSessionLabel(rows)).toBe('2024-25');
  });

  it('returns undefined when every label is null', () => {
    expect(latestSessionLabel([row(null, 'a'), row(null, 'b')])).toBeUndefined();
  });

  it('returns undefined for an empty list', () => {
    expect(latestSessionLabel([])).toBeUndefined();
  });

  it('returns undefined for undefined input', () => {
    expect(latestSessionLabel(undefined)).toBeUndefined();
  });

  it('handles a single row', () => {
    expect(latestSessionLabel([row('2024-25')])).toBe('2024-25');
  });
});
