import { LAYOUT_BORDER } from '@/lib/reports/colors';

interface PerfPillProps {
  pct: string;
  /** Server-stamped fill color from the payload's perf_color, or a
   *  client-computed performanceColor() result. Empty string falls back
   *  to a neutral grey. */
  color: string;
}

/**
 * Performance traffic-light pill rendered inside the rollup tables on the
 * Standard Summary and Strand Summary pages. Background uses the PBIX
 * traffic-light hex (pink/yellow/green or empty → neutral grey), text is
 * always black for contrast, and the pill is bordered to match the table
 * chrome.
 */
export default function PerfPill({ pct, color }: PerfPillProps) {
  return (
    <span
      className="inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-bold"
      style={{
        backgroundColor: color || '#E5E5E5',
        color: '#000',
        border: `1px solid ${LAYOUT_BORDER}`,
      }}
    >
      {pct}
    </span>
  );
}
