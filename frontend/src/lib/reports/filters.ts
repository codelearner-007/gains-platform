'use client';

import { useCallback, useMemo } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';

export interface ReportFilters {
  strand: string | null;
  standard: string | null;
}

export interface UseReportFilters {
  filters: ReportFilters;
  setStrand: (value: string | null) => void;
  setStandard: (value: string | null) => void;
  reset: () => void;
  hasActiveFilter: boolean;
}

type FilterKey = keyof ReportFilters;

// PowerBI selection has two non-obvious behaviors:
// (1) clicking the active value clears it (toggle), so the click handler
// can't be a plain setter; (2) picking strand and standard together would
// over-constrain the dashboard, so setting one clears the other.
export function useReportFilters(): UseReportFilters {
  const router = useRouter();
  const searchParams = useSearchParams();

  const strand = searchParams.get('strand');
  const standard = searchParams.get('standard');
  // Memoise on the raw scalars (not the searchParams instance) so the
  // returned object stays referentially stable until the URL actually
  // changes — downstream `useMemo([data, filters])` chains depend on it.
  const filters: ReportFilters = useMemo(
    () => ({ strand, standard }),
    [strand, standard],
  );

  const setFilter = useCallback(
    (key: FilterKey, value: string | null) => {
      const params = new URLSearchParams(searchParams.toString());
      const current = params.get(key);
      if (!value || current === value) {
        params.delete(key);
      } else {
        params.set(key, value);
        // Picking strand clears standard (and vice-versa) so the
        // dashboard reads as "filtered to this thing".
        const sibling: FilterKey = key === 'strand' ? 'standard' : 'strand';
        params.delete(sibling);
      }
      const next = params.toString();
      if (next === searchParams.toString()) return;
      router.replace(next ? `?${next}` : '?', { scroll: false });
    },
    [router, searchParams],
  );

  const setStrand = useCallback(
    (value: string | null) => setFilter('strand', value),
    [setFilter],
  );
  const setStandard = useCallback(
    (value: string | null) => setFilter('standard', value),
    [setFilter],
  );

  const reset = useCallback(() => {
    if (!strand && !standard) return;
    const params = new URLSearchParams(searchParams.toString());
    params.delete('strand');
    params.delete('standard');
    const next = params.toString();
    router.replace(next ? `?${next}` : '?', { scroll: false });
  }, [router, searchParams, strand, standard]);

  return {
    filters,
    setStrand,
    setStandard,
    reset,
    hasActiveFilter: strand !== null || standard !== null,
  };
}
