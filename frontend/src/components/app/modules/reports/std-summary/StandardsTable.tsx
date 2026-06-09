'use client';

import type { StandardSummaryRollupRow } from '@/lib/reports/types';
import {
  cellColor,
  HEADER_BAR_BG,
  LAYOUT_BORDER,
  performanceColor,
} from '@/lib/reports/colors';
import PerfPill from '../shared/PerfPill';
import {
  tableCellStyle as cellStyle,
  tableHeaderStyle,
} from '../shared/tableStyles';
import { SortableHeader, useTableSort } from '@/lib/reports/useTableSort';

type SortKey =
  | 'schoology_standard'
  | 'strand'
  | 'subject'
  | 'num_questions'
  | 'grade_average';

const SORT_ACCESSORS: Record<
  SortKey,
  (r: StandardSummaryRollupRow) => string | number
> = {
  schoology_standard: (r) => (r.schoology_standard || '').toLowerCase(),
  strand: (r) => (r.strand || '').toLowerCase(),
  subject: (r) => (r.subject || '').toLowerCase(),
  num_questions: (r) => r.num_questions,
  grade_average: (r) => r.grade_average,
};

const INITIAL_DIRECTIONS: Partial<Record<SortKey, 'asc' | 'desc'>> = {
  num_questions: 'desc',
  grade_average: 'desc',
};

interface Props {
  standards: StandardSummaryRollupRow[];
}

export default function StandardsTable({ standards }: Props) {
  // Legacy default: Strand ascending (card-per-standard ordered by strand).
  const { sortedRows: sorted, sortColumn, sortDirection, onHeaderClick } =
    useTableSort<StandardSummaryRollupRow, SortKey>({
      rows: standards,
      accessors: SORT_ACCESSORS,
      defaultColumn: 'strand',
      defaultDirection: 'asc',
      initialDirections: INITIAL_DIRECTIONS,
    });

  return (
    <div
      className="flex flex-col bg-white border"
      style={{ borderColor: LAYOUT_BORDER }}
    >
      <div
        className="px-3 py-1.5 text-[13px] font-bold text-black border-b"
        style={{
          backgroundColor: HEADER_BAR_BG,
          borderColor: LAYOUT_BORDER,
        }}
      >
        Standards rollup ({sorted.length} standards)
      </div>
      <div className="overflow-auto" style={{ maxHeight: 480 }}>
        <table style={{ borderCollapse: 'collapse', width: '100%' }}>
          <thead>
            <tr>
              <th style={tableHeaderStyle}>
                <SortableHeader
                  column="schoology_standard"
                  label="Standard"
                  sortColumn={sortColumn}
                  sortDirection={sortDirection}
                  onClick={onHeaderClick}
                />
              </th>
              <th style={tableHeaderStyle}>
                <SortableHeader
                  column="strand"
                  label="Strand"
                  sortColumn={sortColumn}
                  sortDirection={sortDirection}
                  onClick={onHeaderClick}
                />
              </th>
              <th style={tableHeaderStyle}>
                <SortableHeader
                  column="subject"
                  label="Subject"
                  sortColumn={sortColumn}
                  sortDirection={sortDirection}
                  onClick={onHeaderClick}
                />
              </th>
              <th style={{ ...tableHeaderStyle, textAlign: 'center' }}>
                <SortableHeader
                  column="num_questions"
                  label="# of Questions"
                  sortColumn={sortColumn}
                  sortDirection={sortDirection}
                  onClick={onHeaderClick}
                  align="center"
                />
              </th>
              <th style={{ ...tableHeaderStyle, textAlign: 'center' }}>
                <SortableHeader
                  column="grade_average"
                  label="Grade Avg"
                  sortColumn={sortColumn}
                  sortDirection={sortDirection}
                  onClick={onHeaderClick}
                  align="center"
                />
              </th>
              <th style={{ ...tableHeaderStyle, textAlign: 'center' }}>
                Performance
              </th>
            </tr>
          </thead>
          <tbody>
            {sorted.length === 0 ? (
              <tr>
                <td
                  style={{ ...cellStyle, textAlign: 'center' }}
                  colSpan={6}
                >
                  No standards data
                </td>
              </tr>
            ) : (
              sorted.map((row, idx) => (
                <tr
                  key={`std-${row.schoology_standard}-${row.schoology_standard}-${row.strand}-${idx}`}
                >
                  <td style={{ ...cellStyle, fontWeight: 600 }}>
                    {row.schoology_standard}
                  </td>
                  <td style={cellStyle}>{row.strand}</td>
                  <td style={cellStyle}>{row.subject}</td>
                  <td style={{ ...cellStyle, textAlign: 'center' }}>
                    {row.num_questions}
                  </td>
                  <td
                    style={{
                      ...cellStyle,
                      textAlign: 'center',
                      fontWeight: 600,
                      backgroundColor: cellColor(row.grade_average),
                    }}
                  >
                    {row.grade_average_pct}
                  </td>
                  <td style={{ ...cellStyle, textAlign: 'center' }}>
                    <PerfPill
                      pct={row.grade_average_pct}
                      color={performanceColor(row.grade_average)}
                    />
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
