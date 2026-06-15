'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import {
  useQuery,
  type QueryKey,
  type UseQueryResult,
} from '@tanstack/react-query';

interface UseAssessmentReportArgs<T> {
  /**
   * Whether the URL params required by the report are present
   * (e.g. `!!itemId`, or `!!itemId && !!questionId` for IAD).
   * Drives both the redirect-away guard and react-query `enabled`.
   */
  ready: boolean;
  /**
   * Pre-built query key. Pass the exact `reportsKeys.*(...)` tuple so the
   * key — including the `schoolId` segment — stays byte-identical and
   * school-switch invalidation keeps working.
   */
  queryKey: QueryKey;
  queryFn: () => Promise<T>;
  /** Where to redirect when the report is not `ready`. */
  redirectTo?: string;
}

/**
 * Shared shell for the assessment report pages: owns the `item_id` (etc.)
 * redirect + the react-query wiring that every page repeats verbatim.
 *
 * The query key is passed in fully-built so each page keeps constructing it
 * with its own `reportsKeys.*` helper — this hook never reshapes the key.
 */
export function useAssessmentReport<T>({
  ready,
  queryKey,
  queryFn,
  redirectTo = '/app',
}: UseAssessmentReportArgs<T>): UseQueryResult<T> & { ready: boolean } {
  const router = useRouter();

  useEffect(() => {
    if (!ready) router.replace(redirectTo);
  }, [ready, router, redirectTo]);

  const query = useQuery({
    queryKey,
    queryFn,
    enabled: ready,
  });

  return { ...query, ready };
}
