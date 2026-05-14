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
}: {
  kpis: KPIs;
  strands?: SddStrandRow[];
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
              % per Strand
            </th>
          </tr>
        </thead>
        <tbody>
          {fallback ? (
            <tr>
              <td style={cellStyle}>—</td>
              <td style={{ ...cellStyle, textAlign: 'center' }}>0</td>
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
            rows.map((row, i) => (
              <tr key={`strand-${i}-${row.strand}`}>
                <td style={cellStyle}>{row.strand}</td>
                <td style={{ ...cellStyle, textAlign: 'center' }}>
                  {row.num_standards}
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
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}

export function StandardsTable({
  kpis,
  standards,
}: {
  kpis: KPIs;
  standards?: SddStandardRow[];
}) {
  const rows = useMemo(
    () =>
      (standards ?? []).slice().sort((a, b) => {
        const s = a.strand.localeCompare(b.strand);
        if (s !== 0) return s;
        return a.cpalms_standard.localeCompare(b.cpalms_standard);
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
            <tr>
              <td style={cellStyle}>(All Questions)</td>
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
            rows.map((row, i) => (
              <tr key={`standard-${i}-${row.cpalms_standard}-${row.strand}`}>
                <td style={cellStyle}>{row.cpalms_standard}</td>
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
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}
