import type { CSSProperties } from 'react';
import { GRID_LINE } from '@/lib/reports/colors';

// Standard rollup-table header (12px, 6px-8px padding). Used by SDD
// StandardsTable + QRA Strands_StandardsTables.
export const tableHeaderStyle: CSSProperties = {
  color: '#000',
  fontWeight: 700,
  fontSize: 12,
  padding: '6px 8px',
  textAlign: 'left',
  borderBottom: `1px solid ${GRID_LINE}`,
  backgroundColor: '#FFFFFF',
};

// Standard rollup-table cell. Pairs with `tableHeaderStyle`.
export const tableCellStyle: CSSProperties = {
  borderBottom: `1px solid ${GRID_LINE}`,
  padding: '6px 8px',
  fontSize: 12,
  color: '#000',
};

// Larger variant used by the QRA QuestionDetailTable (8px padding,
// 13px cells, top-aligned for long-form question HTML).
export const tableHeaderStyleLarge: CSSProperties = {
  color: '#000',
  fontWeight: 700,
  fontSize: 12,
  padding: '8px',
  textAlign: 'left',
  borderBottom: `1px solid ${GRID_LINE}`,
  backgroundColor: '#FFFFFF',
  verticalAlign: 'top',
};

export const tableCellStyleLarge: CSSProperties = {
  borderBottom: `1px solid ${GRID_LINE}`,
  padding: '8px',
  fontSize: 13,
  color: '#000',
  verticalAlign: 'top',
  backgroundColor: '#FFFFFF',
};

// ── Frozen-table helpers ───────────────────────────────────────────────────
// Shared sticky-cell factories used with <ScrollableTableContainer>. Generalised
// from the proven inline pattern in qra/QuestionDetailTable. Sticky lives on the
// CELLS (Chrome ignores sticky on <thead>/<tr> under border-collapse), with an
// opaque background to occlude scrolling rows and an inset box-shadow to repaint
// the hairline border that border-collapse drops off a stuck cell. The
// `@media print` block in globals.css resets all of this so PDFs print full.

// Stacking order: body 0 < frozen left column 1 < frozen header 2 < corner 3
// (a corner = a cell that is both in the header row AND a frozen left column).
export const STICKY_Z = { col: 1, header: 2, corner: 3 } as const;

// Fixed widths + cumulative left offsets for the Question Summary matrix's three
// frozen label columns (the only table wide enough to need sticky-left columns).
export const QSM_LABEL_COLS = { instructor: 150, student: 170, score: 70 } as const;
export const QSM_LEFT = { instructor: 0, student: 150, score: 320 } as const;

/**
 * Freeze a `<thead>` cell to the top of the scroll viewport. `top` is 0 for a
 * single header row, or the rendered height of row 1 for the 2nd row of a
 * multi-row header. Supplying `left` makes it a frozen CORNER (top + left).
 */
export function stickyHeaderStyle(
  base: CSSProperties,
  opts: { top?: number; left?: number; border?: string } = {},
): CSSProperties {
  const { top = 0, left, border = GRID_LINE } = opts;
  const shadow = [`inset 0 -1px 0 ${border}`]; // bottom hairline
  if (left !== undefined) shadow.push(`inset -1px 0 0 ${border}`); // right hairline (corner)
  return {
    ...base,
    position: 'sticky',
    top,
    ...(left !== undefined ? { left } : {}),
    zIndex: left !== undefined ? STICKY_Z.corner : STICKY_Z.header,
    boxShadow: shadow.join(', '),
  };
}

/**
 * Freeze a body/label cell to the left edge during horizontal scroll. Requires
 * an opaque `background` (border-collapse cells have none of their own) and a
 * cumulative `left` offset.
 */
export function stickyLeftStyle(
  base: CSSProperties,
  opts: { left: number; background: string; border?: string },
): CSSProperties {
  const { left, background, border = GRID_LINE } = opts;
  return {
    ...base,
    position: 'sticky',
    left,
    zIndex: STICKY_Z.col,
    background,
    boxShadow: `inset -1px 0 0 ${border}`,
  };
}
