'use client';

import { X } from 'lucide-react';
import { cn } from '@/lib/utils';
import { LAYOUT_BORDER } from '@/lib/reports/colors';

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
 * Reusable multi-select pill list — the PBIX `slicer` (data.mode=Basic)
 * equivalent. Each option is a toggle chip; selected chips use the primary
 * accent, the rest stay muted. Accessible via `aria-pressed` + native button
 * keyboard handling.
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
        'flex flex-col gap-1.5 rounded-md border bg-white px-3 py-2',
        className,
      )}
      style={{ borderColor: LAYOUT_BORDER }}
      role="group"
      aria-label={label}
    >
      <div className="flex items-center justify-between gap-2">
        <span className="text-[12px] font-semibold text-black">{label}</span>
        {hasSelection ? (
          <button
            type="button"
            onClick={onClear}
            className="inline-flex items-center gap-1 rounded border border-border bg-white px-1.5 py-0.5 text-[10px] font-medium text-neutral-700 hover:bg-neutral-50 cursor-pointer"
            aria-label={`Clear ${label} filter`}
          >
            <X className="h-3 w-3" aria-hidden="true" />
            Clear
          </button>
        ) : null}
      </div>
      <div className="flex flex-wrap gap-1.5">
        {opts.length === 0 ? (
          <span className="text-[11px] text-neutral-400">No options</span>
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
                  'rounded-full border px-2.5 py-0.5 text-[11px] font-medium transition-colors cursor-pointer select-none focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
                  isSelected
                    ? 'border-primary bg-primary text-primary-foreground hover:bg-primary/90'
                    : 'border-border bg-white text-neutral-700 hover:bg-neutral-100',
                )}
              >
                {o.label ?? o.value}
              </button>
            );
          })
        )}
      </div>
    </div>
  );
}
