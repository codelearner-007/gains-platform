'use client';

import { useMemo } from 'react';
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
  const rows = useMemo(
    () =>
      (strands ?? []).slice().sort((a, b) =>
        a.strand.localeCompare(b.strand),
      ),
    [strands],
  );
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
            <th style={tableHeaderStyle}>Strand</th>
            <th style={{ ...tableHeaderStyle, textAlign: 'center' }}>
              # of Standards
            </th>
            <th style={{ ...tableHeaderStyle, textAlign: 'center' }}>
              # of Questions
            </th>
            <th style={{ ...tableHeaderStyle, textAlign: 'center' }}>
              % per Strand
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
                      backgroundColor: cellColor(row.grade_average),
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
  const rows = useMemo(
    () =>
      (standards ?? []).slice().sort((a, b) => {
        const s = a.strand.localeCompare(b.strand);
        if (s !== 0) return s;
        return a.schoology_standard.localeCompare(b.schoology_standard);
      }),
    [standards],
  );
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
            <th style={tableHeaderStyle}>Standards</th>
            <th style={{ ...tableHeaderStyle, textAlign: 'center' }}>
              # of Questions
            </th>
            <th style={{ ...tableHeaderStyle, textAlign: 'center' }}>
              % per Standard
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
                    backgroundColor: cellColor(row.grade_average),
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
