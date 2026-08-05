import type { ReactNode } from 'react';
import { KPI_CARD_BG, LAYOUT_BORDER } from '@/lib/reports/colors';

/**
 * Shared KPI card used in every report's KPI strip (QRA, SDD, YTD,
 * IAD, Standard Summary, Strand Summary).
 *
 * The card has three customisation points (instead of a hard-coded variant):
 *   - `className`         — outer container overrides (e.g. `min-h-[100px]`).
 *   - `valueClassName`    — value typography overrides (e.g. `text-[24px]`).
 *                           Defaults to `text-[28px]`.
 *   - `backgroundColor`   — fill colour. Defaults to the shared
 *                           `KPI_CARD_BG` (#B8DBFF, sourced from
 *                           `lib/reports/colors`).
 *
 * Pass a multi-line `value` (a React node) if you need to render a list of
 * names inside the card; the value column is centered and stacks vertically.
 */

interface KpiCardProps {
  label: string;
  value: ReactNode;
  /** Override outer container classes (e.g. min-height). */
  className?: string;
  /** Override value typography (e.g. text-[24px]). Default: text-[28px]. */
  valueClassName?: string;
  /** Override background color. Default: KPI_CARD_BG. */
  backgroundColor?: string;
  /** Optional native tooltip explaining how the metric is computed. */
  hint?: string;
}

const baseContainer =
  'flex flex-col items-center justify-center px-3 py-2 rounded-md border h-full';
const baseValue = 'font-bold leading-tight text-black text-center mt-1';

export default function KpiCard({
  label,
  value,
  className = '',
  valueClassName = 'text-[28px]',
  backgroundColor = KPI_CARD_BG,
  hint,
}: KpiCardProps) {
  return (
    <div
      className={`${baseContainer} ${className}`.trim()}
      style={{ backgroundColor, borderColor: LAYOUT_BORDER }}
      title={hint}
    >
      <div className="text-[12px] font-medium text-neutral-700 text-center">
        {label}
      </div>
      <div className={`${baseValue} ${valueClassName}`.trim()}>{value}</div>
    </div>
  );
}
