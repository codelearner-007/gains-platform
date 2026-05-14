'use client';

import { useMemo } from 'react';
import type { YTDHeatmapCell } from '@/lib/reports/types';
import {
  GRID_LINE,
  HEADER_BAR_BG,
  LAYOUT_BORDER,
  performanceColor,
} from '@/lib/reports/colors';
import { formatPercent } from '@/lib/reports/format';

interface Props {
  cells: YTDHeatmapCell[];
}

function decodeStrand(s: string): string {
  return s.replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/&gt;/g, '>');
}

export default function StrandHeatmap({ cells }: Props) {
  const { strands, dates, lookup } = useMemo(() => {
    const strandSet = new Set<string>();
    const dateSet = new Set<string>();
    const lookup = new Map<string, YTDHeatmapCell>();
    for (const c of cells) {
      strandSet.add(c.strand);
      dateSet.add(c.date);
      lookup.set(`${c.strand}::${c.date}`, c);
    }
    return {
      strands: Array.from(strandSet).sort(),
      dates: Array.from(dateSet).sort(),
      lookup,
    };
  }, [cells]);

  return (
    <div
      className="flex flex-col bg-white border"
      style={{ borderColor: LAYOUT_BORDER }}
    >
      <div
        className="px-3 py-1.5 text-[14px] font-bold text-black"
        style={{ backgroundColor: HEADER_BAR_BG }}
      >
        Strand Performance Heatmap
      </div>
      <div className="overflow-auto" style={{ maxHeight: 360 }}>
        {strands.length === 0 || dates.length === 0 ? (
          <div className="p-4 text-sm text-neutral-500">
            No strand data available
          </div>
        ) : (
          <table
            style={{
              borderCollapse: 'separate',
              borderSpacing: 0,
              width: 'max-content',
              minWidth: '100%',
            }}
          >
            <thead>
              <tr>
                <th
                  style={{
                    position: 'sticky',
                    left: 0,
                    top: 0,
                    backgroundColor: '#FFFFFF',
                    zIndex: 3,
                    minWidth: 220,
                    maxWidth: 320,
                    padding: '6px 8px',
                    fontSize: 12,
                    fontWeight: 700,
                    color: '#000',
                    borderBottom: `1px solid ${GRID_LINE}`,
                    borderRight: `1px solid ${GRID_LINE}`,
                    textAlign: 'left',
                  }}
                >
                  Strand
                </th>
                {dates.map((d) => (
                  <th
                    key={d}
                    style={{
                      position: 'sticky',
                      top: 0,
                      backgroundColor: '#FFFFFF',
                      zIndex: 2,
                      minWidth: 80,
                      padding: '6px 8px',
                      fontSize: 11,
                      fontWeight: 700,
                      color: '#000',
                      borderBottom: `1px solid ${GRID_LINE}`,
                      whiteSpace: 'nowrap',
                    }}
                  >
                    <div
                      style={{
                        transform: 'rotate(-45deg)',
                        transformOrigin: 'left bottom',
                        display: 'inline-block',
                        marginBottom: 4,
                      }}
                    >
                      {d}
                    </div>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {strands.map((s) => (
                <tr key={s}>
                  <td
                    style={{
                      position: 'sticky',
                      left: 0,
                      backgroundColor: '#FFFFFF',
                      zIndex: 1,
                      minWidth: 220,
                      maxWidth: 320,
                      padding: '6px 8px',
                      fontSize: 12,
                      color: '#000',
                      borderBottom: `1px solid ${GRID_LINE}`,
                      borderRight: `1px solid ${GRID_LINE}`,
                      whiteSpace: 'nowrap',
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                    }}
                    title={decodeStrand(s)}
                  >
                    {decodeStrand(s)}
                  </td>
                  {dates.map((d) => {
                    const cell = lookup.get(`${s}::${d}`);
                    if (!cell) {
                      return (
                        <td
                          key={`${s}-${d}`}
                          style={{
                            backgroundColor: '#F5F5F5',
                            border: '1px solid #FFFFFF',
                            minWidth: 80,
                            height: 36,
                            textAlign: 'center',
                            fontSize: 11,
                            color: '#999',
                          }}
                        >
                          —
                        </td>
                      );
                    }
                    return (
                      <td
                        key={`${s}-${d}`}
                        style={{
                          backgroundColor: performanceColor(cell.grade_average),
                          border: '1px solid #FFFFFF',
                          minWidth: 80,
                          height: 36,
                          textAlign: 'center',
                          fontSize: 12,
                          fontWeight: 600,
                          color: '#000',
                        }}
                        title={`${decodeStrand(s)} on ${d}: ${formatPercent(cell.grade_average, 1)}`}
                      >
                        {formatPercent(cell.grade_average, 0)}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
