'use client';

import { useCallback, useMemo } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import type {
  StandardSummaryFilters,
  StrandSummaryFilters,
} from './types';

/**
 * The five filter keys shared between the Standard Summary and Strand
 * Summary pages. Strand Summary additionally tracks a `strand` selection
 * outside of this set.
 */
export const SUMMARY_FILTER_KEYS = [
  'session',
  'subject',
  'grade',
  'category',
  'section',
] as const;

type SummaryFilterKey = (typeof SUMMARY_FILTER_KEYS)[number];

/** Common shape – `StandardSummaryFilters` and `StrandSummaryFilters`
 *  are structurally identical. */
type SummaryFilters = StandardSummaryFilters | StrandSummaryFilters;

function readFiltersFromParams<F extends SummaryFilters>(
  params: URLSearchParams,
): F {
  const out: Record<string, string> = {};
  for (const k of SUMMARY_FILTER_KEYS) {
    const v = params.get(k);
    if (v) out[k] = v;
  }
  return out as unknown as F;
}

interface UseSummaryFiltersOptions {
  /** Path to navigate to when filters change (e.g. '/app/reports/standard-summary'). */
  basePath: string;
  /** Extra query params to preserve on every navigation
   *  (e.g. the strand-summary `strand` selection). */
  preserveParams?: Record<string, string | null | undefined>;
}

interface UseSummaryFiltersResult<F extends SummaryFilters> {
  filters: F;
  setFilters: (next: F) => void;
}

/**
 * URL-backed filter state for the school-wide Standard / Strand summary
 * pages. Reads the five `SUMMARY_FILTER_KEYS` from the current
 * `searchParams`, and writes them back via `router.replace` when the
 * caller invokes `setFilters`. Extra params (like the strand-summary
 * row selection) are preserved through `preserveParams`.
 */
export function useSummaryFilters<F extends SummaryFilters>(
  options: UseSummaryFiltersOptions,
): UseSummaryFiltersResult<F> {
  const { basePath, preserveParams } = options;
  const router = useRouter();
  const searchParams = useSearchParams();

  const filters = useMemo<F>(
    () => readFiltersFromParams<F>(searchParams),
    [searchParams],
  );

  const setFilters = useCallback(
    (next: F) => {
      const params = new URLSearchParams();
      for (const k of SUMMARY_FILTER_KEYS) {
        const v = (next as Record<SummaryFilterKey, string | undefined>)[k];
        if (v) params.set(k, v);
      }
      if (preserveParams) {
        for (const [k, v] of Object.entries(preserveParams)) {
          if (v) params.set(k, v);
        }
      }
      router.replace(params.size > 0 ? `${basePath}?${params.toString()}` : basePath);
    },
    [router, basePath, preserveParams],
  );

  return { filters, setFilters };
}
