'use client';

import { useMemo } from 'react';
import type { StrandSummaryStandardRow } from '@/lib/reports/types';
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
  | 'strand'
  | 'schoology_standard'
  | 'num_questions'
  | 'num_assessments'
  | 'grade_average';

const SORT_ACCESSORS: Record<
  SortKey,
  (r: StrandSummaryStandardRow) => string | number
> = {
  // Strand sort keeps the legacy tie-break on standard so rows within a
  // strand stay in standard order.
  strand: (r) =>
    `${(r.strand || '').toLowerCase()}\u0000${(
      r.schoology_standard || ''
    ).toLowerCase()}`,
  schoology_standard: (r) => (r.schoology_standard || '').toLowerCase(),
  num_questions: (r) => r.num_questions,
  num_assessments: (r) => r.num_assessments,
  grade_average: (r) => r.grade_average,
};

const INITIAL_DIRECTIONS: Partial<Record<SortKey, 'asc' | 'desc'>> = {
  num_questions: 'desc',
  num_assessments: 'desc',
  grade_average: 'desc',
};

interface Props {
  standards: StrandSummaryStandardRow[];
  selectedStrand?: string | null;
}

export default function StrandStandardsTable({
  standards,
  selectedStrand,
}: Props) {
  const filtered = useMemo(
    () =>
      selectedStrand
        ? standards.filter((s) => s.strand === selectedStrand)
        : standards,
    [standards, selectedStrand],
  );

  // Legacy default: Strand ascending (with standard tie-break).
  const { sortedRows: sorted, sortColumn, sortDirection, onHeaderClick } =
    useTableSort<StrandSummaryStandardRow, SortKey>({
      rows: filtered,
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
        {selectedStrand
          ? `Standards in "${selectedStrand}" (${sorted.length})`
          : `Standards across all strands (${sorted.length})`}
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
              <th style={tableHeaderStyle}>Cluster</th>
              <th style={{ ...tableHeaderStyle, textAlign: 'center' }}>
                <SortableHeader
                  column="num_questions"
                  label="# Questions"
                  sortColumn={sortColumn}
                  sortDirection={sortDirection}
                  onClick={onHeaderClick}
                  align="center"
                />
              </th>
              <th style={{ ...tableHeaderStyle, textAlign: 'center' }}>
                <SortableHeader
                  column="num_assessments"
                  label="# Assessments"
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
                  colSpan={7}
                >
                  No standards data
                </td>
              </tr>
            ) : (
              sorted.map((row, i) => (
                <tr
                  key={`std-${i}-${row.schoology_standard}-${row.strand}`}
                >
                  <td style={{ ...cellStyle, fontWeight: 600 }}>
                    {row.schoology_standard}
                  </td>
                  <td style={cellStyle}>{row.strand}</td>
                  <td style={cellStyle}>
                    <div
                      className="truncate max-w-[280px]"
                      title={row.cluster}
                    >
                      {row.cluster}
                    </div>
                  </td>
                  <td style={{ ...cellStyle, textAlign: 'center' }}>
                    {row.num_questions}
                  </td>
                  <td style={{ ...cellStyle, textAlign: 'center' }}>
                    {row.num_assessments}
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
