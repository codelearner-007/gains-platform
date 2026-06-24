'use client';

import { Check, Filter, X } from 'lucide-react';
import { cn } from '@/lib/utils';
import { HEADER_BAR_BG, LAYOUT_BORDER } from '@/lib/reports/colors';

export interface SlicerOption {
  value: string;
  label?: string;
}

interface ReportSlicerProps {
  label: string;
  /** Plain string values or {value,label} pairs. */
  options: (string | SlicerOption)[];
  selected: Set<string>;
  onToggle: (value: string) => void;
  onClear: () => void;
  className?: string;
}

function normalize(o: string | SlicerOption): SlicerOption {
  return typeof o === 'string' ? { value: o } : o;
}

/**
 * Reusable multi-select filter bar — the PBIX `slicer` (data.mode=Basic)
 * equivalent. A single tinted band (matching the report's "Summary by
 * Standards" header band) with a leading filter icon + label, inline toggle
 * chips, and a trailing Clear action. Selected chips use the primary accent
 * AND a check glyph (so selection isn't conveyed by color alone); the rest stay
 * muted. Accessible via `aria-pressed` + native button keyboard handling.
 */
export default function ReportSlicer({
  label,
  options,
  selected,
  onToggle,
  onClear,
  className,
}: ReportSlicerProps) {
  const opts = options.map(normalize);
  const hasSelection = selected.size > 0;

  return (
    <div
      className={cn(
        'flex flex-wrap items-center gap-x-2 gap-y-1.5 rounded-md border px-3 py-1.5',
        className,
      )}
      style={{ backgroundColor: HEADER_BAR_BG, borderColor: LAYOUT_BORDER }}
      role="group"
      aria-label={label}
    >
      <span className="inline-flex items-center gap-1.5 text-[12px] font-semibold text-black">
        <Filter className="h-3.5 w-3.5 text-neutral-600" aria-hidden="true" />
        {label}
      </span>
      <span
        className="hidden h-4 w-px bg-neutral-300 sm:inline-block"
        aria-hidden="true"
      />
      {opts.length === 0 ? (
        <span className="text-[11px] text-neutral-500">No options</span>
      ) : (
        opts.map((o) => {
          const isSelected = selected.has(o.value);
          return (
            <button
              key={o.value}
              type="button"
              aria-pressed={isSelected}
              onClick={() => onToggle(o.value)}
              className={cn(
                'inline-flex items-center gap-1 whitespace-nowrap rounded-full border px-2.5 py-1 text-[11px] font-medium transition-colors cursor-pointer select-none focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
                isSelected
                  ? 'border-primary bg-primary text-primary-foreground shadow-sm'
                  : 'border-border bg-white text-neutral-700 hover:border-primary/40 hover:bg-neutral-50',
              )}
            >
              {isSelected ? (
                <Check className="h-3 w-3 shrink-0" aria-hidden="true" />
              ) : null}
              {o.label ?? o.value}
            </button>
          );
        })
      )}
      {hasSelection ? (
        <button
          type="button"
          onClick={onClear}
          className="ml-auto inline-flex items-center gap-1 rounded border border-border bg-white px-2 py-0.5 text-[11px] font-medium text-neutral-700 hover:bg-neutral-50 cursor-pointer"
          aria-label={`Clear ${label} filter`}
        >
          <X className="h-3 w-3" aria-hidden="true" />
          Clear
        </button>
      ) : null}
    </div>
  );
}
