'use client';

import type { CSSProperties } from 'react';
import type {
  ForwardViewStandardRow,
  ForwardViewUnitGroup,
} from '@/lib/reports/types';
import {
  performanceColor,
  STANDARD_HEADER_BG,
  STANDARD_HEADER_FG,
  STRAND_CHIP_BG,
  STRAND_CHIP_FG,
} from '@/lib/reports/colors';
import { formatNumber, formatShortDate } from '@/lib/reports/format';
import {
  tableCellStyle,
  tableHeaderStyle,
} from '@/components/app/modules/reports/shared/tableStyles';

interface UnitStandardsTableProps {
  unit: ForwardViewUnitGroup;
  /** When true, a unit with zero flagged standards collapses to a muted line. */
  flaggedOnly: boolean;
}

const CENTER_CELL: CSSProperties = { ...tableCellStyle, textAlign: 'center' };
const CENTER_HEADER: CSSProperties = { ...tableHeaderStyle, textAlign: 'center' };

/**
 * One assessment (UNIT) card: a header (unit name + assessment date + flagged
 * chip) over a worst-first standards table. Rows arrive pre-sorted from the
 * backend (pct ASC, nulls last) — there is no client-side sorting in v1. The
 * % Correct cell fill uses the FROZEN performance ramp; the "Focus" flag is a
 * separate destructive-tinted pill driven purely by the server `is_troublesome`.
 */
export default function UnitStandardsTable({
  unit,
  flaggedOnly,
}: UnitStandardsTableProps) {
  const collapsed = flaggedOnly && unit.flagged_count === 0;
  const dateStr = formatShortDate(unit.assessment_date);

  return (
    <div className="bg-white border border-border rounded overflow-hidden print:break-inside-avoid">
      <div className="flex items-center justify-between gap-2 px-3 py-2 border-b border-border">
        <div className="flex flex-col min-w-0">
          <span className="text-[13px] font-semibold text-foreground truncate">
            {unit.unit}
          </span>
          {dateStr && (
            <span className="text-[11px] text-muted-foreground">{dateStr}</span>
          )}
        </div>
        {unit.flagged_count > 0 && (
          <span className="inline-flex shrink-0 items-center rounded-full border border-destructive/20 bg-destructive/10 px-2 py-0.5 text-[11px] font-semibold text-destructive">
            {unit.flagged_count} standard{unit.flagged_count === 1 ? '' : 's'}{' '}
            flagged
          </span>
        )}
      </div>

      {collapsed ? (
        <div className="px-3 py-2 text-xs text-muted-foreground">
          No flagged standards in this assessment
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table
            style={{ width: '100%', minWidth: 640, borderCollapse: 'collapse' }}
          >
            <thead>
              <tr>
                <th style={tableHeaderStyle}>Standard</th>
                <th style={tableHeaderStyle}>Description</th>
                <th style={tableHeaderStyle}>Strand</th>
                <th style={CENTER_HEADER}>Questions</th>
                <th style={CENTER_HEADER}>Points</th>
                <th style={CENTER_HEADER}>% Correct</th>
                <th style={CENTER_HEADER}>Flag</th>
              </tr>
            </thead>
            <tbody>
              {unit.standards.map((row, i) => (
                <StandardRow
                  key={`${row.schoology_standard}-${row.strand}-${i}`}
                  row={row}
                />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function StandardRow({ row }: { row: ForwardViewStandardRow }) {
  const code = row.cpalms_standard || row.schoology_standard;
  const showAlias =
    !!row.schoology_standard && row.schoology_standard !== code;
  const ga = row.grade_average;
  const pctCellStyle: CSSProperties =
    ga != null
      ? { ...CENTER_CELL, backgroundColor: performanceColor(ga) }
      : CENTER_CELL;
  const points = `${formatNumber(row.total_score)} / ${formatNumber(row.total_possible_point)}`;

  const chip = (
    <span
      className="inline-flex items-center rounded px-1.5 py-0.5 text-[11px] font-semibold"
      style={{ backgroundColor: STANDARD_HEADER_BG, color: STANDARD_HEADER_FG }}
    >
      {code}
    </span>
  );

  return (
    <tr>
      <td style={{ ...tableCellStyle, whiteSpace: 'nowrap' }}>
        {row.direct_link ? (
          <a
            href={row.direct_link}
            target="_blank"
            rel="noreferrer"
            className="inline-block rounded-sm focus:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            title={`Open ${code} on CPALMS`}
          >
            {chip}
          </a>
        ) : (
          chip
        )}
        {showAlias && (
          <span className="ml-1.5 text-[10px] text-muted-foreground">
            {row.schoology_standard}
          </span>
        )}
      </td>
      <td style={{ ...tableCellStyle, maxWidth: 340 }}>
        <span className="line-clamp-2" title={row.description || undefined}>
          {row.description || ''}
        </span>
      </td>
      <td style={tableCellStyle}>
        {row.strand ? (
          <span
            className="inline-flex items-center rounded px-1.5 py-0.5 text-[11px] font-medium"
            style={{ backgroundColor: STRAND_CHIP_BG, color: STRAND_CHIP_FG }}
          >
            {row.strand}
          </span>
        ) : (
          ''
        )}
      </td>
      <td style={CENTER_CELL} className="tabular-nums">
        {row.num_questions}
      </td>
      <td style={CENTER_CELL} className="tabular-nums whitespace-nowrap">
        {points}
      </td>
      <td style={pctCellStyle} className="tabular-nums font-semibold">
        {ga == null ? '—' : row.grade_average_pct}
      </td>
      <td style={CENTER_CELL}>
        {row.is_troublesome ? (
          <span className="inline-flex items-center rounded-full border border-destructive/20 bg-destructive/10 px-2 py-0.5 text-[10px] font-semibold text-destructive">
            Focus
          </span>
        ) : (
          ''
        )}
      </td>
    </tr>
  );
}
