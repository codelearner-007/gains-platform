'use client';

import { useCallback, useMemo } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';

export interface ReportFilters {
  // Multi-select: zero or more strands AND zero or more standards may be
  // active at once. Empty array == "no filter" for that dimension.
  strands: string[];
  standards: string[];
}

export type ActiveFilterChip = {
  key: 'strand' | 'standard';
  value: string;
};

export interface UseReportFilters {
  filters: ReportFilters;
  /** Toggle a strand in/out of the active strand set (additive). */
  setStrand: (value: string | null) => void;
  /** Toggle a standard in/out of the active standard set (additive). */
  setStandard: (value: string | null) => void;
  /** Clear all active strands, leaving standards untouched. */
  clearStrands: () => void;
  /** Clear all active standards, leaving strands untouched. */
  clearStandards: () => void;
  reset: () => void;
  hasActiveFilter: boolean;
  /** One chip per active value across both dimensions, for the filter bar. */
  activeChips: ActiveFilterChip[];
  isStrandSelected: (value: string) => boolean;
  isStandardSelected: (value: string) => boolean;
}

type FilterKey = keyof ReportFilters;
const PARAM: Record<FilterKey, string> = { strands: 'strand', standards: 'standard' };

// PowerBI's QRA slicer/cross-filter was MULTI-select and combined a strand
// selection WITH a standard selection (they coexist, not mutually exclusive).
// URL encoding mirrors that: `?strand=A,B&standard=MA.912.AR.3.1`. A bare
// scalar (`?strand=A`) parses into a single-element array so legacy deep links
// keep working.
function parseList(raw: string | null): string[] {
  if (!raw) return [];
  return raw
    .split(',')
    .map((s) => s.trim())
    .filter(Boolean);
}

export function useReportFilters(): UseReportFilters {
  const router = useRouter();
  const searchParams = useSearchParams();

  const strandRaw = searchParams.get('strand');
  const standardRaw = searchParams.get('standard');
  // Memoise on the raw scalars (not the searchParams instance) so the
  // returned object stays referentially stable until the URL actually
  // changes — downstream `useMemo([data, filters])` chains depend on it.
  const filters: ReportFilters = useMemo(
    () => ({ strands: parseList(strandRaw), standards: parseList(standardRaw) }),
    [strandRaw, standardRaw],
  );

  const toggle = useCallback(
    (key: FilterKey, value: string | null) => {
      if (!value) return;
      const param = PARAM[key];
      const params = new URLSearchParams(searchParams.toString());
      const current = parseList(params.get(param));
      const next = current.includes(value)
        ? current.filter((v) => v !== value)
        : [...current, value];

      if (next.length === 0) params.delete(param);
      else params.set(param, next.join(','));

      const nextStr = params.toString();
      if (nextStr === searchParams.toString()) return;
      router.replace(nextStr ? `?${nextStr}` : '?', { scroll: false });
    },
    [router, searchParams],
  );

  const setStrand = useCallback(
    (value: string | null) => toggle('strands', value),
    [toggle],
  );
  const setStandard = useCallback(
    (value: string | null) => toggle('standards', value),
    [toggle],
  );

  const clearParam = useCallback(
    (param: string) => {
      if (!searchParams.get(param)) return;
      const params = new URLSearchParams(searchParams.toString());
      params.delete(param);
      const next = params.toString();
      router.replace(next ? `?${next}` : '?', { scroll: false });
    },
    [router, searchParams],
  );

  const clearStrands = useCallback(() => clearParam('strand'), [clearParam]);
  const clearStandards = useCallback(() => clearParam('standard'), [clearParam]);

  const reset = useCallback(() => {
    if (!strandRaw && !standardRaw) return;
    const params = new URLSearchParams(searchParams.toString());
    params.delete('strand');
    params.delete('standard');
    const next = params.toString();
    router.replace(next ? `?${next}` : '?', { scroll: false });
  }, [router, searchParams, strandRaw, standardRaw]);

  const activeChips: ActiveFilterChip[] = useMemo(
    () => [
      ...filters.strands.map((value) => ({ key: 'strand' as const, value })),
      ...filters.standards.map((value) => ({ key: 'standard' as const, value })),
    ],
    [filters.strands, filters.standards],
  );

  const isStrandSelected = useCallback(
    (value: string) => filters.strands.includes(value),
    [filters.strands],
  );
  const isStandardSelected = useCallback(
    (value: string) => filters.standards.includes(value),
    [filters.standards],
  );

  return {
    filters,
    setStrand,
    setStandard,
    clearStrands,
    clearStandards,
    reset,
    hasActiveFilter: filters.strands.length > 0 || filters.standards.length > 0,
    activeChips,
    isStrandSelected,
    isStandardSelected,
  };
}
