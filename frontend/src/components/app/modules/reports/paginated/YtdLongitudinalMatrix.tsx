'use client';

import { useMemo } from 'react';
import type {
  YearToDatePerformancePayload,
  YtdCell,
  YtdStandardTotal,
  YtdStudentRow,
  YtdTeacherGroup,
} from '@/lib/reports/types';
import {
  GRID_LINE,
  PBIX_ACCENT_NAVY,
  PBIX_ACCENT_LIGHT_BLUE,
  GROUP_HEADER_CYAN,
  REPORT_TEXT_DARK,
} from '@/lib/reports/colors';
import {
  SortableHeader,
  sortRowsBy,
  useSharedSort,
  type SortDirection,
} from '@/lib/reports/useTableSort';

/**
 * Legacy "Longitudinal Report - Year To Date" paginated matrix (PBIX ord
 * 8/9/10). One row per (Classroom Instructor → Student), one column per
 * standard assessed YTD. Cells are POINTS-based — Score = received/possible
 * (e.g. "4/7"), % = SUM(received)/SUM(possible) at every grain. Per-teacher
 * subtotal rows ("# Correct Answers" / "Score %") follow each group, and
 * grand-total rows ("Possible Points" / "# Correct Answers" / "Score %")
 * close the report. The legacy YTD PDFs are NOT colour-banded (unlike QSR),
 * so cells render plain.
 *
 * Variant differences (purely presentational):
 *   • 1 — Tests Taken column + per-standard Score AND %
 *   • 2 — no Tests Taken, per-standard % only
 *   • 3 — Tests Taken + Score AND % + assessment/unit name under each code
 */
export type YtdVariant = 1 | 2 | 3;

interface Props {
  payload: YearToDatePerformancePayload;
  variant: YtdVariant;
}

const fmtPct = (p: number) => `${Math.round(p * 100)}%`;
const fmtPts = (n: number) =>
  Number.isInteger(n) ? String(n) : n.toFixed(1).replace(/\.0$/, '');
const fmtScore = (c: YtdCell) =>
  `${fmtPts(c.points_received)}/${fmtPts(c.points_possible)}`;

type YtdSortKey =
  | 'none'
  | 'instructor'
  | 'student'
  | 'score'
  | 'tests_taken'
  | 'points_possible'
  | 'points_received';

const STUDENT_ACCESSORS: Record<
  Exclude<YtdSortKey, 'instructor' | 'none'>,
  (s: YtdStudentRow) => string | number | null
> = {
  student: (s) => (s.user_name || '').toLowerCase(),
  score: (s) => s.score_pct ?? null,
  tests_taken: (s) => s.tests_taken ?? null,
  points_possible: (s) => s.points_possible ?? null,
  points_received: (s) => s.points_received ?? null,
};

export default function YtdLongitudinalMatrix({ payload, variant }: Props) {
  const { standards, teacher_groups, grand_total } = payload;
  const showTestsTaken = variant === 1 || variant === 3;
  const showScore = variant === 1 || variant === 3;
  const showUnitNames = variant === 3;
  // V1/V3 standard columns span two sub-columns (Score, %); V2 spans one (%).
  const subCols = showScore ? 2 : 1;

  // Fixed row-label columns are click-to-sortable (legacy tableEx matrix).
  // Default ('none') keeps the server/legacy row order — which is already the
  // legacy score-ascending teacher-group + standard-column order. "Classroom
  // Instructors" reorders teacher groups; the rest reorder students WITHIN each
  // group. Per-standard matrix columns are not row-sortable.
  const { sortColumn, sortDirection, onHeaderClick } = useSharedSort<YtdSortKey>(
    'none',
    'asc',
  );

  const orderedGroups = useMemo(() => {
    if (sortColumn !== 'instructor') return teacher_groups;
    return sortRowsBy(
      teacher_groups,
      (g: YtdTeacherGroup) => (g.section_instructor || '').toLowerCase(),
      sortDirection,
    );
  }, [teacher_groups, sortColumn, sortDirection]);

  const border = `1px solid ${GRID_LINE}`;
  const headStyle = {
    backgroundColor: PBIX_ACCENT_NAVY,
    color: '#fff',
    border,
  } as const;
  const subHeadStyle = {
    backgroundColor: PBIX_ACCENT_LIGHT_BLUE,
    // Dark text on the light-blue sub-header band (white was 2.35:1, fails AA;
    // slate-800 ≈ 6.3:1, passes AA). The navy headStyle above keeps white (4.72:1).
    color: REPORT_TEXT_DARK,
    border,
  } as const;

  return (
    <div className="overflow-x-auto bg-white print:overflow-visible">
      <table className="report-wide-matrix border-collapse text-[11px] text-black">
        <thead>
          {/* Row 1: standard codes (span sub-cols) + leading/trailing labels */}
          <tr>
            <th rowSpan={2} className="px-2 py-1 text-left align-bottom" style={headStyle}>
              <SortableHeader column="instructor" label="Classroom Instructors" sortColumn={sortColumn} sortDirection={sortDirection} onClick={onHeaderClick} className="text-white" />
            </th>
            <th rowSpan={2} className="px-2 py-1 text-left align-bottom" style={headStyle}>
              <SortableHeader column="student" label="Student Name" sortColumn={sortColumn} sortDirection={sortDirection} onClick={onHeaderClick} className="text-white" />
            </th>
            <th rowSpan={2} className="px-2 py-1 align-bottom" style={headStyle}>
              <SortableHeader column="score" label="Score %" sortColumn={sortColumn} sortDirection={sortDirection} onClick={onHeaderClick} align="center" className="text-white" />
            </th>
            {showTestsTaken && (
              <th rowSpan={2} className="px-2 py-1 align-bottom" style={headStyle}>
                <SortableHeader column="tests_taken" label="Tests Taken" sortColumn={sortColumn} sortDirection={sortDirection} onClick={onHeaderClick} align="center" className="text-white" />
              </th>
            )}
            {standards.map((s) => (
              <th
                key={s.standard_label}
                colSpan={subCols}
                className="px-2 py-1 text-center"
                style={headStyle}
              >
                <div>{s.standard_label}</div>
                {showUnitNames && s.unit_names && (
                  <div className="text-[9px] font-normal leading-tight opacity-90">
                    {s.unit_names}
                  </div>
                )}
              </th>
            ))}
            <th rowSpan={2} className="px-2 py-1 align-bottom" style={headStyle}>
              <SortableHeader column="points_possible" label="Possible Points" sortColumn={sortColumn} sortDirection={sortDirection} onClick={onHeaderClick} align="center" className="text-white" />
            </th>
            <th rowSpan={2} className="px-2 py-1 align-bottom" style={headStyle}>
              <SortableHeader column="points_received" label="# Correct Answers" sortColumn={sortColumn} sortDirection={sortDirection} onClick={onHeaderClick} align="center" className="text-white" />
            </th>
          </tr>
          {/* Row 2: per-standard Score / % sub-headers */}
          <tr>
            {standards.map((s) =>
              showScore ? (
                [
                  <th key={`${s.standard_label}-score`} className="px-2 py-0.5" style={subHeadStyle}>
                    Score
                  </th>,
                  <th key={`${s.standard_label}-pct`} className="px-2 py-0.5" style={subHeadStyle}>
                    %
                  </th>,
                ]
              ) : (
                <th key={`${s.standard_label}-pct`} className="px-2 py-0.5" style={subHeadStyle}>
                  %
                </th>
              ),
            )}
          </tr>
        </thead>

        <tbody>
          {orderedGroups.map((tg) => (
            <TeacherBlock
              key={tg.section_instructor}
              group={tg}
              standards={standards}
              showTestsTaken={showTestsTaken}
              showScore={showScore}
              subCols={subCols}
              border={border}
              sortColumn={sortColumn}
              sortDirection={sortDirection}
            />
          ))}

          {/* Grand-total rows */}
          <tr style={{ backgroundColor: GROUP_HEADER_CYAN }}>
            <td className="px-2 py-1 font-semibold" colSpan={showTestsTaken ? 4 : 3} style={{ border }}>
              Possible Points
            </td>
            {standards.map((s) => (
              <StdFootCell
                key={`gpp-${s.standard_label}`}
                total={grand_total.standard_totals[s.standard_label]}
                kind="possible"
                showScore={showScore}
                border={border}
              />
            ))}
            <td className="px-2 py-1 text-center font-semibold" style={{ border }}>
              {fmtPts(grand_total.points_possible)}
            </td>
            <td className="px-2 py-1 text-center font-semibold" style={{ border }}>
              {fmtPts(grand_total.points_received)}
            </td>
          </tr>
          <tr style={{ backgroundColor: GROUP_HEADER_CYAN }}>
            <td className="px-2 py-1 font-semibold" colSpan={showTestsTaken ? 4 : 3} style={{ border }}>
              # Correct Answers
            </td>
            {standards.map((s) => (
              <StdFootCell
                key={`gca-${s.standard_label}`}
                total={grand_total.standard_totals[s.standard_label]}
                kind="received"
                showScore={showScore}
                border={border}
              />
            ))}
            <td className="px-2 py-1" style={{ border }} />
            <td className="px-2 py-1 text-center font-semibold" style={{ border }}>
              {fmtPts(grand_total.points_received)}
            </td>
          </tr>
          <tr style={{ backgroundColor: GROUP_HEADER_CYAN }}>
            <td className="px-2 py-1 font-semibold" colSpan={showTestsTaken ? 4 : 3} style={{ border }}>
              Score %
            </td>
            {standards.map((s) => (
              <StdFootCell
                key={`gsp-${s.standard_label}`}
                total={grand_total.standard_totals[s.standard_label]}
                kind="pct"
                showScore={showScore}
                border={border}
              />
            ))}
            <td className="px-2 py-1" style={{ border }} />
            <td className="px-2 py-1 text-center font-semibold" style={{ border }}>
              {fmtPct(grand_total.score_pct)}
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  );
}

function TeacherBlock({
  group,
  standards,
  showTestsTaken,
  showScore,
  subCols,
  border,
  sortColumn,
  sortDirection,
}: {
  group: YearToDatePerformancePayload['teacher_groups'][number];
  standards: YearToDatePerformancePayload['standards'];
  showTestsTaken: boolean;
  showScore: boolean;
  subCols: number;
  border: string;
  sortColumn: YtdSortKey;
  sortDirection: SortDirection;
}) {
  const totalCols =
    (showTestsTaken ? 4 : 3) + standards.length * subCols + 2;
  const students =
    sortColumn === 'instructor' || sortColumn === 'none'
      ? group.students
      : sortRowsBy(group.students, STUDENT_ACCESSORS[sortColumn], sortDirection);
  return (
    <>
      {/* Teacher group header — instructor name + overall % */}
      <tr style={{ backgroundColor: GROUP_HEADER_CYAN }}>
        <td colSpan={totalCols} className="px-2 py-1 font-semibold" style={{ border }}>
          {group.section_instructor}{' '}
          <span className="font-normal text-neutral-700">
            {fmtPct(group.teacher_score_pct)}
          </span>
        </td>
      </tr>

      {students.map((st) => (
        <tr key={st.user_uid}>
          <td className="px-2 py-1" style={{ border }} />
          <td className="px-2 py-1 whitespace-nowrap" style={{ border }}>
            {st.user_name}
          </td>
          <td className="px-2 py-1 text-center" style={{ border }}>
            {fmtPct(st.score_pct)}
          </td>
          {showTestsTaken && (
            <td className="px-2 py-1 text-center" style={{ border }}>
              {st.tests_taken}
            </td>
          )}
          {standards.map((s) => {
            const cell = st.cells[s.standard_label];
            if (showScore) {
              return [
                <td key={`${s.standard_label}-sc`} className="px-2 py-1 text-center" style={{ border }}>
                  {cell ? fmtScore(cell) : '-'}
                </td>,
                <td key={`${s.standard_label}-pc`} className="px-2 py-1 text-center" style={{ border }}>
                  {cell ? fmtPct(cell.score_pct) : '-'}
                </td>,
              ];
            }
            return (
              <td key={`${s.standard_label}-pc`} className="px-2 py-1 text-center" style={{ border }}>
                {cell ? fmtPct(cell.score_pct) : '-'}
              </td>
            );
          })}
          <td className="px-2 py-1 text-center" style={{ border }}>
            {fmtPts(st.points_possible)}
          </td>
          <td className="px-2 py-1 text-center" style={{ border }}>
            {fmtPts(st.points_received)}
          </td>
        </tr>
      ))}

      {/* Per-teacher subtotal: # Correct Answers + Score % */}
      <tr>
        <td className="px-2 py-1" style={{ border }} />
        <td className="px-2 py-1 font-semibold" style={{ border }}>
          # Correct Answers
        </td>
        <td className="px-2 py-1" style={{ border }} />
        {showTestsTaken && <td className="px-2 py-1" style={{ border }} />}
        {standards.map((s) => (
          <StdFootCell
            key={`tca-${s.standard_label}`}
            total={group.standard_subtotals[s.standard_label]}
            kind="received"
            showScore={showScore}
            border={border}
          />
        ))}
        <td className="px-2 py-1" style={{ border }} />
        <td className="px-2 py-1" style={{ border }} />
      </tr>
      <tr>
        <td className="px-2 py-1" style={{ border }} />
        <td className="px-2 py-1 font-semibold" style={{ border }}>
          Score %
        </td>
        <td className="px-2 py-1 text-center font-semibold" style={{ border }}>
          {fmtPct(group.teacher_score_pct)}
        </td>
        {showTestsTaken && <td className="px-2 py-1" style={{ border }} />}
        {standards.map((s) => (
          <StdFootCell
            key={`tsp-${s.standard_label}`}
            total={group.standard_subtotals[s.standard_label]}
            kind="pct"
            showScore={showScore}
            border={border}
          />
        ))}
        <td className="px-2 py-1" style={{ border }} />
        <td className="px-2 py-1" style={{ border }} />
      </tr>
    </>
  );
}

/**
 * A per-standard footer cell. In Score+% variants the value occupies the
 * first sub-column and the second sub-column is left blank (mirrors the
 * legacy footer, which prints a single number spanning the pair).
 */
function StdFootCell({
  total,
  kind,
  showScore,
  border,
}: {
  total: YtdStandardTotal | undefined;
  kind: 'possible' | 'received' | 'pct';
  showScore: boolean;
  border: string;
}) {
  let value = '';
  if (total) {
    if (kind === 'pct') value = fmtPct(total.score_pct);
    else if (kind === 'received') value = fmtPts(total.points_received);
    else value = fmtPts(total.points_possible);
  }
  return (
    <>
      <td className="px-2 py-1 text-center font-semibold" style={{ border }}>
        {value}
      </td>
      {showScore && <td className="px-2 py-1" style={{ border }} />}
    </>
  );
}
