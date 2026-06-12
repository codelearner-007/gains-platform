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
