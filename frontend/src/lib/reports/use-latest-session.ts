'use client';

import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { reportsApi, reportsKeys } from '@/lib/reports/api-client';
import type { SessionRow } from '@/lib/reports/types';

/** Leading academic year of a "YYYY-YY" session label; -Infinity if unparseable. */
function sessionStartYear(label: string): number {
  const m = /^(\d{4})/.exec(label);
  return m ? Number(m[1]) : Number.NEGATIVE_INFINITY;
}

/**
 * Pure resolver for the latest (most recent) session label in a `dim_session`
 * list. Picks the label with the greatest leading academic year so the result
 * is order-independent AND correct across a century boundary — a plain lexical
 * max would wrongly rank "2099-00" above "2100-01". Ties and unparseable labels
 * fall back to a lexical tiebreak. Returns `undefined` when nothing to resolve.
 */
export function latestSessionLabel(
  rows: readonly SessionRow[] | undefined,
): string | undefined {
  if (!rows || rows.length === 0) return undefined;
  const labels = rows
    .map((r) => r.session)
    .filter((s): s is string => Boolean(s));
  if (labels.length === 0) return undefined;
  return labels.reduce((latest, s) => {
    const ys = sessionStartYear(s);
    const yl = sessionStartYear(latest);
    if (ys !== yl) return ys > yl ? s : latest;
    return s > latest ? s : latest; // same start year → stable lexical tiebreak
  });
}

/**
 * The session a yearly report should use: an explicit `?session` override when
 * present, else the school's latest session. Centralizes the
 * `filters.session ?? latest` default shared by all four yearly report pages.
 *
 * `sessionsPending` is true while the sessions list is still loading, so a page
 * can show a spinner *only* until sessions settle — never indefinitely when a
 * school has no sessions at all (which would otherwise strand a session-gated
 * query on a permanent loading state).
 */
export function useEffectiveSession(
  schoolId: string | null | undefined,
  sessionOverride: string | undefined,
): { session: string | undefined; sessionsPending: boolean } {
  const q = useQuery({
    queryKey: reportsKeys.sessions(schoolId ?? undefined),
    queryFn: () => reportsApi.sessions(schoolId ?? undefined),
  });
  const latest = useMemo(() => latestSessionLabel(q.data), [q.data]);
  return { session: sessionOverride ?? latest, sessionsPending: q.isPending };
}
