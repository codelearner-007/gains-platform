'use client';

import type {
  KPIs,
  SddStandardRow,
  SddStrandRow,
} from '@/lib/reports/types';
import { cellColor, HEADER_BAR_BG, LAYOUT_BORDER } from '@/lib/reports/colors';
import { formatPercent } from '@/lib/reports/format';
import {
  tableCellStyle as cellStyle,
  tableHeaderStyle,
} from '../shared/tableStyles';
import { SortableHeader, useTableSort } from '@/lib/reports/useTableSort';

type StrandSortKey = 'strand' | 'num_standards' | 'num_questions' | 'grade_average';
type StandardSortKey = 'schoology_standard' | 'num_questions' | 'grade_average';

// Unassessed rows (grade_average === null) sort as -1 so they sink to the
// bottom on ascending order, matching the "blank cell last" reading order.
const STRAND_SORT_ACCESSORS: Record<StrandSortKey, (r: SddStrandRow) => string | number> = {
  strand: (r) => r.strand.toLowerCase(),
  num_standards: (r) => r.num_standards,
  num_questions: (r) => r.num_questions,
  grade_average: (r) => r.grade_average ?? -1,
};

const STANDARD_SORT_ACCESSORS: Record<StandardSortKey, (r: SddStandardRow) => string | number> = {
  schoology_standard: (r) => r.schoology_standard.toLowerCase(),
  num_questions: (r) => r.num_questions,
  grade_average: (r) => r.grade_average ?? -1,
};

export function SummaryByStandardsHeader() {
  return (
    <div
      className="px-3 py-1.5 text-[14px] font-bold text-black"
      style={{ backgroundColor: HEADER_BAR_BG }}
    >
      Summary by Standards
    </div>
  );
}

export function StrandsTable({
  kpis,
  strands,
  selectedStrand,
  onSelectStrand,
}: {
  kpis: KPIs;
  strands?: SddStrandRow[];
  selectedStrand?: string | null;
  onSelectStrand?: (strand: string) => void;
}) {
  const { sortedRows: rows, sortColumn, sortDirection, onHeaderClick } =
    useTableSort<SddStrandRow, StrandSortKey>({
      rows: strands ?? [],
      accessors: STRAND_SORT_ACCESSORS,
      defaultColumn: 'strand',
      defaultDirection: 'asc',
    });
  const fallback = rows.length === 0;
  const value = kpis.grade_average;

  return (
    <div
      className="flex flex-col bg-white border"
      style={{ borderColor: LAYOUT_BORDER }}
    >
      <div
        className="px-3 py-1.5 text-[13px] font-bold text-black border-b"
        style={{ backgroundColor: HEADER_BAR_BG, borderColor: LAYOUT_BORDER }}
      >
        Correct % by Strands
      </div>
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
                label="# of Standards"
                sortColumn={sortColumn}
                sortDirection={sortDirection}
                onClick={onHeaderClick}
                align="center"
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
                label="% per Strand"
                sortColumn={sortColumn}
                sortDirection={sortDirection}
                onClick={onHeaderClick}
                align="center"
              />
            </th>
          </tr>
        </thead>
        <tbody>
          {fallback ? (
            // Defensive fallback only — backend ``_synthesize_other_rollups``
            // already emits an "Other" row for unaligned assessments so
            // this branch should never render in production. Kept for
            // robustness against stale payloads or future regressions.
            <tr>
              <td style={cellStyle}>Other</td>
              <td style={{ ...cellStyle, textAlign: 'center' }}>1</td>
              <td style={{ ...cellStyle, textAlign: 'center' }}>
                {kpis.total_questions ?? 0}
              </td>
              <td
                style={{
                  ...cellStyle,
                  textAlign: 'center',
                  fontWeight: 600,
                  backgroundColor: cellColor(value),
                }}
              >
                {formatPercent(value, 1)}
              </td>
            </tr>
          ) : (
            rows.map((row, i) => {
              const isSelected = selectedStrand === row.strand;
              const dim = !!selectedStrand && !isSelected;
              return (
                <tr
                  key={`strand-${i}-${row.strand}`}
                  onClick={() => onSelectStrand?.(row.strand)}
                  role={onSelectStrand ? 'button' : undefined}
                  tabIndex={onSelectStrand ? 0 : undefined}
                  onKeyDown={(e) => {
                    if (
                      onSelectStrand &&
                      (e.key === 'Enter' || e.key === ' ')
                    ) {
                      e.preventDefault();
                      onSelectStrand(row.strand);
                    }
                  }}
                  className={
                    isSelected ? 'ring-2 ring-neutral-800 ring-inset' : undefined
                  }
                  style={{
                    cursor: onSelectStrand ? 'pointer' : 'default',
                    opacity: dim ? 0.45 : 1,
                  }}
                >
                  <td style={cellStyle}>{row.strand}</td>
                  <td style={{ ...cellStyle, textAlign: 'center' }}>
                    {row.num_standards}
                  </td>
                  <td style={{ ...cellStyle, textAlign: 'center' }}>
                    {row.num_questions}
                  </td>
                  <td
                    style={{
                      ...cellStyle,
                      textAlign: 'center',
                      fontWeight: 600,
                      // Unassessed strand → blank cell, no traffic-light fill.
                      backgroundColor:
                        row.grade_average == null
                          ? undefined
                          : cellColor(row.grade_average),
                    }}
                  >
                    {row.grade_average_pct}
                  </td>
                </tr>
              );
            })
          )}
        </tbody>
      </table>
    </div>
  );
}

export function StandardsTable({
  kpis,
  standards,
  selectedStandard,
  onSelectStandard,
}: {
  kpis: KPIs;
  standards?: SddStandardRow[];
  selectedStandard?: string | null;
  onSelectStandard?: (schoology_standard: string) => void;
}) {
  const { sortedRows: rows, sortColumn, sortDirection, onHeaderClick } =
    useTableSort<SddStandardRow, StandardSortKey>({
      rows: standards ?? [],
      accessors: STANDARD_SORT_ACCESSORS,
      defaultColumn: 'schoology_standard',
      defaultDirection: 'asc',
    });
  const fallback = rows.length === 0;
  const value = kpis.grade_average;

  return (
    <div
      className="flex flex-col bg-white border"
      style={{ borderColor: LAYOUT_BORDER }}
    >
      <div
        className="px-3 py-1.5 text-[13px] font-bold text-black border-b"
        style={{ backgroundColor: HEADER_BAR_BG, borderColor: LAYOUT_BORDER }}
      >
        Correct % by Standards
      </div>
      <table style={{ borderCollapse: 'collapse', width: '100%' }}>
        <thead>
          <tr>
            <th style={tableHeaderStyle}>
              <SortableHeader
                column="schoology_standard"
                label="Standards"
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
                label="% per Standard"
                sortColumn={sortColumn}
                sortDirection={sortDirection}
                onClick={onHeaderClick}
                align="center"
              />
            </th>
          </tr>
        </thead>
        <tbody>
          {fallback ? (
            // Defensive fallback only — see StrandsTable above.
            <tr>
              <td style={cellStyle}>Other</td>
              <td style={{ ...cellStyle, textAlign: 'center' }}>
                {kpis.total_questions}
              </td>
              <td
                style={{
                  ...cellStyle,
                  textAlign: 'center',
                  fontWeight: 600,
                  backgroundColor: cellColor(value),
                }}
              >
                {formatPercent(value, 1)}
              </td>
            </tr>
          ) : (
            rows.map((row, i) => {
              const isSelected = selectedStandard === row.schoology_standard;
              const dim = !!selectedStandard && !isSelected;
              return (
              <tr
                key={`standard-${i}-${row.schoology_standard}-${row.strand}`}
                onClick={() => onSelectStandard?.(row.schoology_standard)}
                role={onSelectStandard ? 'button' : undefined}
                tabIndex={onSelectStandard ? 0 : undefined}
                onKeyDown={(e) => {
                  if (
                    onSelectStandard &&
                    (e.key === 'Enter' || e.key === ' ')
                  ) {
                    e.preventDefault();
                    onSelectStandard(row.schoology_standard);
                  }
                }}
                className={
                  isSelected ? 'ring-2 ring-neutral-800 ring-inset' : undefined
                }
                style={{
                  cursor: onSelectStandard ? 'pointer' : 'default',
                  opacity: dim ? 0.45 : 1,
                }}
              >
                <td style={cellStyle}>{row.schoology_standard}</td>
                <td style={{ ...cellStyle, textAlign: 'center' }}>
                  {row.num_questions}
                </td>
                <td
                  style={{
                    ...cellStyle,
                    textAlign: 'center',
                    fontWeight: 600,
                    // Unassessed alias standard → blank cell, no fill.
                    backgroundColor:
                      row.grade_average == null
                        ? undefined
                        : cellColor(row.grade_average),
                  }}
                >
                  {row.grade_average_pct}
                </td>
              </tr>
              );
            })
          )}
        </tbody>
      </table>
    </div>
  );
}
