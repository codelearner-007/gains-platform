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
  stickyHeaderStyle,
} from '../shared/tableStyles';
import ScrollableTableContainer from '../shared/ScrollableTableContainer';
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
  selectedStrands,
  onSelectStrand,
}: {
  kpis: KPIs;
  strands?: SddStrandRow[];
  // Multi-select: every active strand value. A clicked row toggles membership.
  selectedStrands?: string[];
  onSelectStrand?: (strand: string) => void;
}) {
  const selectedSet = new Set(selectedStrands ?? []);
  const hasSelection = selectedSet.size > 0;
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
      <ScrollableTableContainer maxHeight="60vh">
      <table style={{ borderCollapse: 'collapse', width: '100%' }}>
        <thead>
          <tr>
            <th style={stickyHeaderStyle(tableHeaderStyle, { top: 0 })}>
              <SortableHeader
                column="strand"
                label="Strand"
                title="Strand"
                description="The broad content area grouping related standards."
                sortColumn={sortColumn}
                sortDirection={sortDirection}
                onClick={onHeaderClick}
              />
            </th>
            <th style={stickyHeaderStyle({ ...tableHeaderStyle, textAlign: 'center' }, { top: 0 })}>
              <SortableHeader
                column="num_standards"
                label="# of Standards"
                title="Number of Standards"
                description="Count of distinct standards that fall under this strand."
                sortColumn={sortColumn}
                sortDirection={sortDirection}
                onClick={onHeaderClick}
                align="center"
              />
            </th>
            <th style={stickyHeaderStyle({ ...tableHeaderStyle, textAlign: 'center' }, { top: 0 })}>
              <SortableHeader
                column="num_questions"
                label="# of Questions"
                title="Number of Questions"
                description="Count of assessment questions tagged to this strand."
                sortColumn={sortColumn}
                sortDirection={sortDirection}
                onClick={onHeaderClick}
                align="center"
              />
            </th>
            <th style={stickyHeaderStyle({ ...tableHeaderStyle, textAlign: 'center' }, { top: 0 })}>
              <SortableHeader
                column="grade_average"
                label="% per Strand"
                title="Correct % per Strand"
                description="Average percent of students answering correctly across this strand's questions."
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
              const isSelected = selectedSet.has(row.strand);
              const dim = hasSelection && !isSelected;
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
      </ScrollableTableContainer>
    </div>
  );
}

export function StandardsTable({
  kpis,
  standards,
  selectedStandards,
  onSelectStandard,
}: {
  kpis: KPIs;
  standards?: SddStandardRow[];
  // Multi-select: every active standard code. A clicked row toggles membership.
  selectedStandards?: string[];
  onSelectStandard?: (schoology_standard: string) => void;
}) {
  const selectedSet = new Set(selectedStandards ?? []);
  const hasSelection = selectedSet.size > 0;
  // PBIX dropped rows whose Grade_Average_Standard_Measure was null (the
  // visual-level "is not blank" filter). Mirror it: hide unassessed Schoology
  // aliases (grade_average === null) so the table shows only scored standards.
  const assessed = (standards ?? []).filter((r) => r.grade_average != null);
  const { sortedRows: rows, sortColumn, sortDirection, onHeaderClick } =
    useTableSort<SddStandardRow, StandardSortKey>({
      rows: assessed,
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
      <ScrollableTableContainer maxHeight="60vh">
      <table style={{ borderCollapse: 'collapse', width: '100%' }}>
        <thead>
          <tr>
            <th style={stickyHeaderStyle(tableHeaderStyle, { top: 0 })}>
              <SortableHeader
                column="schoology_standard"
                label="Standards"
                title="Standard"
                description="The individual learning standard/skill code (e.g. MA.912.A) measured."
                sortColumn={sortColumn}
                sortDirection={sortDirection}
                onClick={onHeaderClick}
              />
            </th>
            <th style={stickyHeaderStyle({ ...tableHeaderStyle, textAlign: 'center' }, { top: 0 })}>
              <SortableHeader
                column="num_questions"
                label="# of Questions"
                title="Number of Questions"
                description="Count of assessment questions tagged to this standard."
                sortColumn={sortColumn}
                sortDirection={sortDirection}
                onClick={onHeaderClick}
                align="center"
              />
            </th>
            <th style={stickyHeaderStyle({ ...tableHeaderStyle, textAlign: 'center' }, { top: 0 })}>
              <SortableHeader
                column="grade_average"
                label="% per Standard"
                title="Correct % per Standard"
                description="Average percent of students answering correctly across this standard's questions."
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
              const isSelected = selectedSet.has(row.schoology_standard);
              const dim = hasSelection && !isSelected;
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
      </ScrollableTableContainer>
    </div>
  );
}
