'use client';

import type { StrandSummaryRollupRow } from '@/lib/reports/types';
import {
  cellColor,
  HEADER_BAR_BG,
  LAYOUT_BORDER,
  performanceColor,
  STRAND_CHIP_BG,
  STRAND_CHIP_FG,
} from '@/lib/reports/colors';
import PerfPill from '../shared/PerfPill';
import {
  tableCellStyle as cellStyle,
  tableHeaderStyle,
} from '../shared/tableStyles';
import { SortableHeader, useTableSort } from '@/lib/reports/useTableSort';

type SortKey =
  | 'strand'
  | 'num_standards'
  | 'num_questions'
  | 'num_assessments'
  | 'subjects'
  | 'grade_average'
  | 'performance';

const SORT_ACCESSORS: Record<
  SortKey,
  (r: StrandSummaryRollupRow) => string | number
> = {
  strand: (r) => (r.strand || '').toLowerCase(),
  num_standards: (r) => r.num_standards,
  num_questions: (r) => r.num_questions,
  num_assessments: (r) => r.num_assessments,
  // Sort by the rendered subject-chip order (joined, lowercased).
  subjects: (r) => (r.subjects || []).join(', ').toLowerCase(),
  grade_average: (r) => r.grade_average,
  // Performance band tracks the underlying grade average.
  performance: (r) => r.grade_average,
};

const INITIAL_DIRECTIONS: Partial<Record<SortKey, 'asc' | 'desc'>> = {
  num_standards: 'desc',
  num_questions: 'desc',
  num_assessments: 'desc',
  grade_average: 'desc',
  performance: 'desc',
};

interface Props {
  strands: StrandSummaryRollupRow[];
  selectedStrand?: string | null;
  onSelectStrand?: (strand: string | null) => void;
}

export default function StrandRollupTable({
  strands,
  selectedStrand,
  onSelectStrand,
}: Props) {
  // Legacy default: Strand ascending.
  const { sortedRows: sorted, sortColumn, sortDirection, onHeaderClick } =
    useTableSort<StrandSummaryRollupRow, SortKey>({
      rows: strands,
      accessors: SORT_ACCESSORS,
      defaultColumn: 'strand',
      defaultDirection: 'asc',
      initialDirections: INITIAL_DIRECTIONS,
    });

  const clickable = !!onSelectStrand;

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
        Strand rollup ({sorted.length} strand{sorted.length === 1 ? '' : 's'})
        {clickable && (
          <span className="ml-2 text-[11px] font-normal text-neutral-700">
            (click a row to filter standards below)
          </span>
        )}
      </div>
      <div className="overflow-auto" style={{ maxHeight: 360 }}>
        <table style={{ borderCollapse: 'collapse', width: '100%' }}>
          <thead>
            <tr>
              <th style={tableHeaderStyle}>
                <SortableHeader
                  column="strand"
                  label="Strand"
                  sortColumn={sortColumn}
                  sortDirection={sortDirection}
                  onClick={onHeaderClick}
                />
              </th>
              <th style={{ ...tableHeaderStyle, textAlign: 'center' }}>
                <SortableHeader
                  column="num_standards"
                  label="# Standards"
                  sortColumn={sortColumn}
                  sortDirection={sortDirection}
                  onClick={onHeaderClick}
                  align="center"
                />
              </th>
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
              <th style={tableHeaderStyle}>
                <SortableHeader
                  column="subjects"
                  label="Subjects"
                  sortColumn={sortColumn}
                  sortDirection={sortDirection}
                  onClick={onHeaderClick}
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
                <SortableHeader
                  column="performance"
                  label="Performance"
                  sortColumn={sortColumn}
                  sortDirection={sortDirection}
                  onClick={onHeaderClick}
                  align="center"
                />
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
                  No strand data
                </td>
              </tr>
            ) : (
              sorted.map((row) => {
                const isSelected = selectedStrand === row.strand;
                return (
                  <tr
                    key={`strand-row-${row.strand}`}
                    onClick={() => {
                      if (!onSelectStrand) return;
                      onSelectStrand(isSelected ? null : row.strand);
                    }}
                    style={{
                      cursor: clickable ? 'pointer' : 'default',
                      backgroundColor: isSelected
                        ? STRAND_CHIP_BG
                        : 'transparent',
                    }}
                  >
                    <td style={{ ...cellStyle, fontWeight: 600 }}>
                      {row.strand}
                    </td>
                    <td style={{ ...cellStyle, textAlign: 'center' }}>
                      {row.num_standards}
                    </td>
                    <td style={{ ...cellStyle, textAlign: 'center' }}>
                      {row.num_questions}
                    </td>
                    <td style={{ ...cellStyle, textAlign: 'center' }}>
                      {row.num_assessments}
                    </td>
                    <td style={cellStyle}>
                      <div className="flex flex-wrap gap-1">
                        {row.subjects.map((s) => (
                          <span
                            key={s}
                            className="inline-flex items-center rounded px-1.5 py-0.5 text-[10px] font-medium"
                            style={{
                              backgroundColor: STRAND_CHIP_BG,
                              color: STRAND_CHIP_FG,
                            }}
                          >
                            {s}
                          </span>
                        ))}
                      </div>
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
                );
              })
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
