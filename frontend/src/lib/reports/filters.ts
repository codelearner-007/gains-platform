'use client';

import { useCallback, useMemo } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';

export interface ReportFilters {
  // Multi-select: zero or more strands AND zero or more standards may be
  // active at once. Empty array == "no filter" for that dimension.
  strands: string[];
  standards: string[];
  // Section instructors (merged-report-only views, e.g. interactive QRA / SDD).
  // Narrows the merged multi-section report to the selected instructor(s).
  instructors: string[];
}

export type ActiveFilterChip = {
  key: 'strand' | 'standard' | 'instructor';
  value: string;
};

export interface UseReportFilters {
  filters: ReportFilters;
  /** Toggle a strand in/out of the active strand set (additive). */
  setStrand: (value: string | null) => void;
  /** Toggle a standard in/out of the active standard set (additive). */
  setStandard: (value: string | null) => void;
  /** Toggle an instructor in/out of the active instructor set (additive). */
  setInstructor: (value: string | null) => void;
  /** Remove one active filter chip, dispatching to the right dimension. */
  removeChip: (chip: ActiveFilterChip) => void;
  /** Clear all active strands, leaving other dimensions untouched. */
  clearStrands: () => void;
  /** Clear all active standards, leaving other dimensions untouched. */
  clearStandards: () => void;
  /** Clear all active instructors, leaving other dimensions untouched. */
  clearInstructors: () => void;
  reset: () => void;
  hasActiveFilter: boolean;
  /** One chip per active value across all dimensions, for the filter bar. */
  activeChips: ActiveFilterChip[];
  isStrandSelected: (value: string) => boolean;
  isStandardSelected: (value: string) => boolean;
  isInstructorSelected: (value: string) => boolean;
}

type FilterKey = keyof ReportFilters;
const PARAM: Record<FilterKey, string> = {
  strands: 'strand',
  standards: 'standard',
  instructors: 'instructor',
};

// PowerBI's QRA slicer/cross-filter was MULTI-select and combined a strand
// selection WITH a standard selection (they coexist, not mutually exclusive).
// URL encoding mirrors that: `?strand=A,B&standard=MA.912.AR.3.1`. A bare
// scalar (`?strand=A`) parses into a single-element array so legacy deep links
// keep working. The instructor slicer (merged-report views) follows the same
// `?instructor=Name1,Name2` form.
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
  const instructorRaw = searchParams.get('instructor');
  // Memoise on the raw scalars (not the searchParams instance) so the
  // returned object stays referentially stable until the URL actually
  // changes — downstream `useMemo([data, filters])` chains depend on it.
  const filters: ReportFilters = useMemo(
    () => ({
      strands: parseList(strandRaw),
      standards: parseList(standardRaw),
      instructors: parseList(instructorRaw),
    }),
    [strandRaw, standardRaw, instructorRaw],
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
  const setInstructor = useCallback(
    (value: string | null) => toggle('instructors', value),
    [toggle],
  );

  const removeChip = useCallback(
    (chip: ActiveFilterChip) => {
      if (chip.key === 'strand') setStrand(chip.value);
      else if (chip.key === 'standard') setStandard(chip.value);
      else setInstructor(chip.value);
    },
    [setStrand, setStandard, setInstructor],
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
  const clearInstructors = useCallback(
    () => clearParam('instructor'),
    [clearParam],
  );

  const reset = useCallback(() => {
    if (!strandRaw && !standardRaw && !instructorRaw) return;
    const params = new URLSearchParams(searchParams.toString());
    params.delete('strand');
    params.delete('standard');
    params.delete('instructor');
    const next = params.toString();
    router.replace(next ? `?${next}` : '?', { scroll: false });
  }, [router, searchParams, strandRaw, standardRaw, instructorRaw]);

  const activeChips: ActiveFilterChip[] = useMemo(
    () => [
      ...filters.strands.map((value) => ({ key: 'strand' as const, value })),
      ...filters.standards.map((value) => ({ key: 'standard' as const, value })),
      ...filters.instructors.map((value) => ({
        key: 'instructor' as const,
        value,
      })),
    ],
    [filters.strands, filters.standards, filters.instructors],
  );

  const isStrandSelected = useCallback(
    (value: string) => filters.strands.includes(value),
    [filters.strands],
  );
  const isStandardSelected = useCallback(
    (value: string) => filters.standards.includes(value),
    [filters.standards],
  );
  const isInstructorSelected = useCallback(
    (value: string) => filters.instructors.includes(value),
    [filters.instructors],
  );

  return {
    filters,
    setStrand,
    setStandard,
    setInstructor,
    removeChip,
    clearStrands,
    clearStandards,
    clearInstructors,
    reset,
    hasActiveFilter:
      filters.strands.length > 0 ||
      filters.standards.length > 0 ||
      filters.instructors.length > 0,
    activeChips,
    isStrandSelected,
    isStandardSelected,
    isInstructorSelected,
  };
}
