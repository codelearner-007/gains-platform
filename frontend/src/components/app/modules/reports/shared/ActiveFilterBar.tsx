'use client';

import { X } from 'lucide-react';
import { HEADER_BAR_BG, LAYOUT_BORDER } from '@/lib/reports/colors';
import type { ReportFilters } from '@/lib/reports/filters';

interface ActiveFilterBarProps {
  filters: ReportFilters;
  onClear: () => void;
}

export default function ActiveFilterBar({
  filters,
  onClear,
}: ActiveFilterBarProps) {
  if (!filters.strand && !filters.standard) return null;

  return (
    <div
      className="mb-2 flex items-center gap-3 rounded-md border px-3 py-1.5 text-[12px]"
      style={{ backgroundColor: HEADER_BAR_BG, borderColor: LAYOUT_BORDER }}
      role="status"
      aria-live="polite"
    >
      <span className="font-semibold text-black">Filtered:</span>
      {filters.standard ? (
        <span className="text-black">
          <span className="text-neutral-700">Standard =</span>{' '}
          <span className="font-semibold">{filters.standard}</span>
        </span>
      ) : filters.strand ? (
        <span className="text-black">
          <span className="text-neutral-700">Strand =</span>{' '}
          <span className="font-semibold">{filters.strand}</span>
        </span>
      ) : null}
      <button
        type="button"
        onClick={onClear}
        className="ml-auto inline-flex items-center gap-1 rounded border bg-white px-2 py-0.5 text-[11px] font-medium text-black hover:bg-neutral-50 cursor-pointer"
        style={{ borderColor: LAYOUT_BORDER }}
        aria-label="Clear filter"
      >
        <X className="h-3 w-3" aria-hidden="true" />
        Clear
      </button>
    </div>
  );
}
