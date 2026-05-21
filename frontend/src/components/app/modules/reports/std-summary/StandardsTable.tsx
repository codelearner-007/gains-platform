'use client';

import { useMemo, useState } from 'react';
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

type SortKey =
  | 'schoology_standard'
  | 'strand'
  | 'subject'
  | 'num_questions'
  | 'grade_average';

interface Props {
  standards: StandardSummaryRollupRow[];
}

export default function StandardsTable({ standards }: Props) {
  const [sortKey, setSortKey] = useState<SortKey>('strand');
  const [sortDesc, setSortDesc] = useState(false);

  const sorted = useMemo(() => {
    const copy = [...standards];
    copy.sort((a, b) => {
      let cmp = 0;
      if (sortKey === 'num_questions' || sortKey === 'grade_average') {
        cmp = (a[sortKey] as number) - (b[sortKey] as number);
      } else {
        cmp = String(a[sortKey] ?? '').localeCompare(String(b[sortKey] ?? ''));
      }
      return sortDesc ? -cmp : cmp;
    });
    return copy;
  }, [standards, sortKey, sortDesc]);

  function toggleSort(key: SortKey) {
    if (key === sortKey) {
      setSortDesc((d) => !d);
    } else {
      setSortKey(key);
      setSortDesc(key === 'num_questions' || key === 'grade_average');
    }
  }

  const headerWith = (label: string, key: SortKey, align: 'left' | 'center' = 'left') => (
    <th
      style={{
        ...tableHeaderStyle,
        textAlign: align,
        cursor: 'pointer',
        userSelect: 'none',
      }}
      onClick={() => toggleSort(key)}
      title={`Sort by ${label}`}
    >
      {label}
      {sortKey === key && (
        <span className="ml-1 text-[10px] text-neutral-500">
          {sortDesc ? '▼' : '▲'}
        </span>
      )}
    </th>
  );

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
              {headerWith('Standard', 'schoology_standard')}
              {headerWith('Strand', 'strand')}
              {headerWith('Subject', 'subject')}
              {headerWith('# of Questions', 'num_questions', 'center')}
              {headerWith('Grade Avg', 'grade_average', 'center')}
              <th
                style={{ ...tableHeaderStyle, textAlign: 'center' }}
              >
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
                      color={
                        row.perf_color ||
                        performanceColor(row.grade_average)
                      }
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
