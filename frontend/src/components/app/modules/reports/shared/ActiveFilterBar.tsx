'use client';

import { X } from 'lucide-react';
import { HEADER_BAR_BG, LAYOUT_BORDER } from '@/lib/reports/colors';
import type { ActiveFilterChip } from '@/lib/reports/filters';

interface ActiveFilterBarProps {
  chips: ActiveFilterChip[];
  /** Remove a single value (toggle it off). */
  onRemove: (chip: ActiveFilterChip) => void;
  /** Remove every active value. */
  onClear: () => void;
}

const CHIP_LABEL: Record<ActiveFilterChip['key'], string> = {
  strand: 'Strand',
  standard: 'Standard',
};

export default function ActiveFilterBar({
  chips,
  onRemove,
  onClear,
}: ActiveFilterBarProps) {
  if (chips.length === 0) return null;

  return (
    <div
      className="mb-2 flex flex-wrap items-center gap-2 rounded-md border px-3 py-1.5 text-[12px]"
      style={{ backgroundColor: HEADER_BAR_BG, borderColor: LAYOUT_BORDER }}
      role="status"
      aria-live="polite"
    >
      <span className="font-semibold text-black">Filtered:</span>
      {chips.map((chip) => (
        <span
          key={`${chip.key}-${chip.value}`}
          className="inline-flex items-center gap-1 rounded-full border bg-white px-2 py-0.5 text-[11px] text-black"
          style={{ borderColor: LAYOUT_BORDER }}
        >
          <span className="text-neutral-600">{CHIP_LABEL[chip.key]}:</span>
          <span className="font-semibold">{chip.value}</span>
          <button
            type="button"
            onClick={() => onRemove(chip)}
            className="inline-flex items-center rounded-full p-0.5 text-neutral-500 hover:bg-neutral-100 hover:text-black cursor-pointer"
            aria-label={`Remove ${CHIP_LABEL[chip.key]} ${chip.value}`}
          >
            <X className="h-3 w-3" aria-hidden="true" />
          </button>
        </span>
      ))}
      <button
        type="button"
        onClick={onClear}
        className="ml-auto inline-flex items-center gap-1 rounded border bg-white px-2 py-0.5 text-[11px] font-medium text-black hover:bg-neutral-50 cursor-pointer"
        style={{ borderColor: LAYOUT_BORDER }}
        aria-label="Clear all filters"
      >
        <X className="h-3 w-3" aria-hidden="true" />
        Clear all
      </button>
    </div>
  );
}
