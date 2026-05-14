'use client';

import { useMemo, useState } from 'react';
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

type SortKey =
  | 'strand'
  | 'num_standards'
  | 'num_questions'
  | 'num_assessments'
  | 'grade_average';

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
  const [sortKey, setSortKey] = useState<SortKey>('strand');
  const [sortDesc, setSortDesc] = useState(false);

  const sorted = useMemo(() => {
    const copy = [...strands];
    copy.sort((a, b) => {
      let cmp = 0;
      if (sortKey === 'strand') {
        cmp = a.strand.localeCompare(b.strand);
      } else {
        cmp = (a[sortKey] as number) - (b[sortKey] as number);
      }
      return sortDesc ? -cmp : cmp;
    });
    return copy;
  }, [strands, sortKey, sortDesc]);

  function toggleSort(key: SortKey) {
    if (key === sortKey) {
      setSortDesc((d) => !d);
    } else {
      setSortKey(key);
      setSortDesc(key !== 'strand');
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
              {headerWith('Strand', 'strand')}
              {headerWith('# Standards', 'num_standards', 'center')}
              {headerWith('# Questions', 'num_questions', 'center')}
              {headerWith(
                '# Assessments',
                'num_assessments',
                'center',
              )}
              <th style={tableHeaderStyle}>Subjects</th>
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
                        color={
                          row.perf_color ||
                          performanceColor(row.grade_average)
                        }
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
