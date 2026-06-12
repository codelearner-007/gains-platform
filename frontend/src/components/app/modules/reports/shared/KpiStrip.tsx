import type { ReactNode } from 'react';
import KpiCard from '@/components/app/modules/reports/shared/KpiCard';

/** Shared min-height applied to every KPI tile across reports. */
export const KPI_CARD_CLASSNAME = 'min-h-[100px]';

/**
 * Per-report responsive column counts.
 *
 * Tailwind needs literal class strings, so each supported count maps to its
 * exact breakpoint chain. These strings reproduce each report's original grid
 * verbatim — do NOT collapse them into a dynamic `grid-cols-${n}` template.
 *   - 5 → SDD, Standard Summary
 *   - 6 → Strand Summary, IAD
 *   - 7 → QRA (uses md:4 then xl:7)
 */
const COLS_CLASS: Record<5 | 6 | 7, string> = {
  5: 'grid-cols-2 sm:grid-cols-3 lg:grid-cols-5',
  6: 'grid-cols-2 sm:grid-cols-3 lg:grid-cols-6',
  7: 'grid-cols-2 sm:grid-cols-3 md:grid-cols-4 xl:grid-cols-7',
};

export interface KpiTile {
  label: string;
  value: ReactNode;
  /** Value typography override (e.g. text-[24px]). */
  valueClassName: string;
}

interface KpiStripProps {
  /** Final column count at the largest breakpoint (5/6/7). */
  cols: 5 | 6 | 7;
  tiles: KpiTile[];
}

/**
 * Shared KPI strip wrapper: the `grid ... gap-2 w-full h-full` container plus
 * the per-tile `min-h-[100px]` card sizing, shared by the grid-based report
 * strips (QRA, SDD, Standard Summary, Strand Summary, IAD).
 */
export default function KpiStrip({ cols, tiles }: KpiStripProps) {
  return (
    <div className={`grid ${COLS_CLASS[cols]} gap-2 w-full h-full`}>
      {tiles.map((tile, i) => (
        <KpiCard
          key={i}
          className={KPI_CARD_CLASSNAME}
          valueClassName={tile.valueClassName}
          label={tile.label}
          value={tile.value}
        />
      ))}
    </div>
  );
}
