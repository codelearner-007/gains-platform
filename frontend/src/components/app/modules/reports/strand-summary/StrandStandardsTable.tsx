'use client';

import { useMemo, useState } from 'react';
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

type SortKey =
  | 'strand'
  | 'cpalms_standard'
  | 'num_questions'
  | 'num_assessments'
  | 'grade_average';

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
  const [sortKey, setSortKey] = useState<SortKey>('strand');
  const [sortDesc, setSortDesc] = useState(false);

  const sorted = useMemo(() => {
    const copy = [...filtered];
    copy.sort((a, b) => {
      let cmp = 0;
      if (sortKey === 'strand' || sortKey === 'cpalms_standard') {
        cmp = String(a[sortKey] ?? '').localeCompare(
          String(b[sortKey] ?? ''),
        );
        if (sortKey === 'strand' && cmp === 0) {
          cmp = a.cpalms_standard.localeCompare(b.cpalms_standard);
        }
      } else {
        cmp = (a[sortKey] as number) - (b[sortKey] as number);
      }
      return sortDesc ? -cmp : cmp;
    });
    return copy;
  }, [filtered, sortKey, sortDesc]);

  function toggleSort(key: SortKey) {
    if (key === sortKey) {
      setSortDesc((d) => !d);
    } else {
      setSortKey(key);
      setSortDesc(
        key === 'num_questions' ||
          key === 'num_assessments' ||
          key === 'grade_average',
      );
    }
  }

  const headerWith = (
    label: string,
    key: SortKey,
    align: 'left' | 'center' = 'left',
  ) => (
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
        {selectedStrand
          ? `Standards in "${selectedStrand}" (${sorted.length})`
          : `Standards across all strands (${sorted.length})`}
      </div>
      <div className="overflow-auto" style={{ maxHeight: 480 }}>
        <table style={{ borderCollapse: 'collapse', width: '100%' }}>
          <thead>
            <tr>
              {headerWith('Standard', 'cpalms_standard')}
              {headerWith('Strand', 'strand')}
              <th style={tableHeaderStyle}>Cluster</th>
              {headerWith('# Questions', 'num_questions', 'center')}
              {headerWith(
                '# Assessments',
                'num_assessments',
                'center',
              )}
              {headerWith('Grade Avg', 'grade_average', 'center')}
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
                  key={`std-${i}-${row.cpalms_standard}-${row.strand}`}
                >
                  <td style={{ ...cellStyle, fontWeight: 600 }}>
                    {row.cpalms_standard}
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
