import type { CSSProperties } from 'react';
import { GRID_LINE, HEADER_BAR_BG, LAYOUT_BORDER } from '@/lib/reports/colors';

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

/**
 * Freeze a `<thead>` cell to the top of a <ScrollableTableContainer> so the
 * column headers stay visible while the table scrolls. Sticky lives on the CELL
 * (Chrome ignores sticky on `<thead>`/`<tr>` under border-collapse); the cell's
 * opaque background occludes scrolling rows and the inset box-shadow repaints
 * the bottom hairline that border-collapse drops off a stuck cell. `top` is 0
 * for a single header row, or the measured height of row 1 for the 2nd row of a
 * stacked header. In paged media sticky falls back to static, so print is fine.
 */
export function stickyHeaderStyle(
  base: CSSProperties,
  opts: { top?: number; border?: string } = {},
): CSSProperties {
  const { top = 0, border = GRID_LINE } = opts;
  return {
    ...base,
    position: 'sticky',
    top,
    zIndex: 2,
    boxShadow: `inset 0 -1px 0 ${border}`,
  };
}

// Shared sticky header-band cell for the paginated QRA tables (QraPaginatedTable,
// QraByTeacherTable, QraByStandardTeacherTable). The band bg lives on each <th>
// because a <tr> bg won't paint behind a sticky cell.
export const STICKY_HEADER_BAND = stickyHeaderStyle(
  { backgroundColor: HEADER_BAR_BG, borderColor: LAYOUT_BORDER },
  { top: 0, border: LAYOUT_BORDER },
);
