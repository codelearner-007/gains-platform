'use client';

import { useMemo } from 'react';
import type { SddStandardRow, SddStrandRow } from '@/lib/reports/types';
import { cellColor, HEADER_BAR_BG, LAYOUT_BORDER } from '@/lib/reports/colors';
import {
  tableCellStyle as cellStyle,
  tableHeaderStyle,
} from '../shared/tableStyles';

export function StrandsRollupTable({ strands }: { strands: SddStrandRow[] }) {
  const sorted = useMemo(
    () => [...strands].sort((a, b) => a.strand.localeCompare(b.strand)),
    [strands],
  );
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
      <div className="overflow-auto" style={{ maxHeight: 320 }}>
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
            {sorted.length === 0 ? (
              <tr>
                <td
                  style={{ ...cellStyle, textAlign: 'center' }}
                  colSpan={4}
                >
                  No strand data
                </td>
              </tr>
            ) : (
              sorted.map((row, i) => (
                <tr key={`strand-${i}-${row.strand}`}>
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
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export function StandardsRollupTable({
  standards,
}: {
  standards: SddStandardRow[];
}) {
  const sorted = useMemo(
    () =>
      [...standards].sort((a, b) => {
        const s = a.strand.localeCompare(b.strand);
        if (s !== 0) return s;
        return a.schoology_standard.localeCompare(b.schoology_standard);
      }),
    [standards],
  );
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
      <div className="overflow-auto" style={{ maxHeight: 320 }}>
        <table style={{ borderCollapse: 'collapse', width: '100%' }}>
          <thead>
            <tr>
              <th style={tableHeaderStyle}>cPalms Standard</th>
              <th style={tableHeaderStyle}>Strand</th>
              <th style={{ ...tableHeaderStyle, textAlign: 'center' }}>
                # of Questions
              </th>
              <th style={{ ...tableHeaderStyle, textAlign: 'center' }}>
                % per Standard
              </th>
            </tr>
          </thead>
          <tbody>
            {sorted.length === 0 ? (
              <tr>
                <td
                  style={{ ...cellStyle, textAlign: 'center' }}
                  colSpan={4}
                >
                  No standards data
                </td>
              </tr>
            ) : (
              sorted.map((row, i) => (
                <tr key={`standard-${i}-${row.schoology_standard}-${row.strand}`}>
                  <td style={cellStyle}>{row.schoology_standard}</td>
                  <td style={cellStyle}>{row.strand}</td>
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
    </div>
  );
}
