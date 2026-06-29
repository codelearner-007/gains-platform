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
 * horizontal (when the table is wider) scroll; the sticky `<thead>` cells that
 * keep the column headers frozen live on the cells themselves (see
 * `stickyHeaderStyle` in tableStyles.ts), not here.
 *
 * Print-safe via inline utilities only: `print:overflow-visible print:!max-h-none`
 * (the `!` beats the inline maxHeight) drop the cap + clipping so the exported
 * PDF shows the full table — `position: sticky` falls back to static in paged
 * media, so no extra print CSS is needed.
 */
export default function ScrollableTableContainer({
  children,
  maxHeight = '72vh',
  className = '',
  style,
}: Props) {
  return (
    <div
      className={`w-full overflow-auto print:overflow-visible print:!max-h-none ${className}`}
      style={{ maxHeight, ...style }}
    >
      {children}
    </div>
  );
}
