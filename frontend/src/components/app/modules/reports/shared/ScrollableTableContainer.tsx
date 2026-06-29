'use client';

import type { CSSProperties, ReactNode } from 'react';

interface Props {
  children: ReactNode;
  /**
   * On-screen height cap; the table scrolls vertically inside. Dropped in print
   * so the PDF renders the full table. Default '72vh' (viewport-relative so it
   * auto-shrinks on small screens). Use '60vh' for compact in-grid tables.
   */
  maxHeight?: number | string;
  /** Extra classes for the viewport (e.g. the table card chrome 'bg-white border'). */
  className?: string;
  style?: CSSProperties;
}

/**
 * The single scroll viewport every per-assessment report table wraps its
 * `<table>` in. `overflow-auto` gives BOTH vertical (within the height cap) and
 * horizontal (when the table is wider) scroll; the sticky `<thead>`/first-column
 * cells that keep headers + labels frozen live on the cells themselves (see
 * `stickyHeaderStyle` / `stickyLeftStyle` in tableStyles.ts), not here.
 *
 * Print-safe: `print:overflow-visible print:!max-h-none` (the `!` beats the
 * inline maxHeight) plus the `.report-scroll` rules in globals.css `@media print`
 * drop the cap, the scrollbars, and the per-cell sticky so the exported PDF
 * shows the complete, static table.
 */
export default function ScrollableTableContainer({
  children,
  maxHeight = '72vh',
  className = '',
  style,
}: Props) {
  return (
    <div
      className={`report-scroll w-full overflow-auto print:overflow-visible print:!max-h-none ${className}`}
      style={{ maxHeight, ...style }}
    >
      {children}
    </div>
  );
}
