'use client';

import { useEffect, useState } from 'react';

/**
 * Stable instructor roster for the merged interactive reports (QRA interactive
 * + SDD). The instructor filter is applied SERVER-SIDE, so the filtered payload
 * narrows `kpis.instructors` to the active selection — which would shrink the
 * slicer's options. This latches the FULL roster captured from an unfiltered
 * load (and resets it when the assessment changes) so the slicer keeps offering
 * every instructor while a filter is active.
 */
export function useInstructorRoster(
  data: { kpis: { instructors: string[] } } | undefined,
  selectedCount: number,
  itemId: string | null,
): string[] {
  const [roster, setRoster] = useState<string[]>([]);
  useEffect(() => setRoster([]), [itemId]);
  useEffect(() => {
    if (data && selectedCount === 0) setRoster(data.kpis.instructors);
  }, [data, selectedCount]);
  return roster;
}
