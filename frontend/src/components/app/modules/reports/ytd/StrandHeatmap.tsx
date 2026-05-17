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

// "2026-04-21" → "Apr 21"; "2026-04-21T…" tolerated; non-ISO inputs return as-is.
function formatHeatmapHeader(raw: string): string {
  const iso = raw.length >= 10 ? raw.slice(0, 10) : raw;
  const d = new Date(`${iso}T00:00:00`);
  if (Number.isNaN(d.getTime())) return raw;
  return d.toLocaleDateString(undefined, {
    month: 'short',
    day: 'numeric',
  });
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
                    minWidth: 240,
                    maxWidth: 340,
                    padding: '8px 10px',
                    fontSize: 13,
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
                      padding: '8px',
                      fontSize: 12,
                      fontWeight: 700,
                      color: '#000',
                      borderBottom: `1px solid ${GRID_LINE}`,
                      whiteSpace: 'nowrap',
                      textAlign: 'center',
                    }}
                    title={d}
                  >
                    {formatHeatmapHeader(d)}
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
                      minWidth: 240,
                      maxWidth: 340,
                      padding: '8px 10px',
                      fontSize: 13,
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
                            height: 40,
                            textAlign: 'center',
                            fontSize: 12,
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
                          height: 40,
                          textAlign: 'center',
                          fontSize: 13,
                          fontWeight: 700,
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
