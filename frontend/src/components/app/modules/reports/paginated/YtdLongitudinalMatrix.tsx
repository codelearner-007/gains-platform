'use client';

import { useLayoutEffect, useMemo, useRef, useState, type CSSProperties } from 'react';
import type {
  YearToDatePerformancePayload,
  YtdCell,
  YtdStandardTotal,
  YtdStudentRow,
  YtdTeacherGroup,
} from '@/lib/reports/types';
import {
  GRID_LINE,
  LAYOUT_BORDER,
  PBIX_ACCENT_NAVY,
  PBIX_ACCENT_LIGHT_BLUE,
  GROUP_HEADER_CYAN,
  REPORT_TEXT_DARK,
  QSR_POINTS_GREY,
  qsrPerformanceColor,
} from '@/lib/reports/colors';
import {
  SortableHeader,
  sortRowsBy,
  useSharedSort,
  type SortDirection,
} from '@/lib/reports/useTableSort';
import ScrollableTableContainer from '@/components/app/modules/reports/shared/ScrollableTableContainer';
import { stickyHeaderStyle } from '@/components/app/modules/reports/shared/tableStyles';

/**
 * Legacy "Longitudinal Report - Year To Date" paginated matrix (PBIX ord
 * 8/9/10). One row per (Classroom Instructor → Student), one column per
 * standard assessed YTD. Cells are POINTS-based — Score = received/possible
 * (e.g. "4/7"), % = SUM(received)/SUM(possible) at every grain. Per-teacher
 * subtotal rows ("# Correct Answers" / "Score %") follow each group, and
 * grand-total rows ("Possible Points" / "# Correct Answers" / "Score %")
 * close the report. Cells carry the legacy SSRS perf 3-color banding
 * (verbatim RDL BackgroundColor IIf → exact hexes via qsrPerformanceColor):
 * Student Name / Score% / Tests-Taken and the subtotal/grand Score% band on
 * the student's mastery Score%; each per-standard "%" cell bands on its own
 * mastery value (received/possible, same scale as the subtotal it sits under);
 * the raw-points helper cells (Score n/N, Possible Points, # Correct) use the
 * neutral legacy grey.
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

  // Freeze BOTH header rows while the matrix scrolls inside the container. Row 2
  // sticks just below row 1, so its `top` is the measured height of row 1
  // (font/zoom-dependent, hence measured not hardcoded). No frozen left columns
  // (their pixel offsets aren't guaranteed under auto table-layout) — they
  // scroll horizontally with the body, matching the other per-assessment tables.
  const row1Ref = useRef<HTMLTableRowElement>(null);
  const [row1H, setRow1H] = useState(28);
  useLayoutEffect(() => {
    const el = row1Ref.current;
    if (!el) return;
    const sync = () => setRow1H(el.offsetHeight);
    sync();
    const ro = new ResizeObserver(sync);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

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
  // Sticky variants: row 1 pins to the top of the scroll viewport, row 2 pins
  // just below it (measured row1H). Applied to the CELLS (border-collapse
  // ignores sticky on <tr>). In print, sticky falls back to static.
  const stickyHead: CSSProperties = stickyHeaderStyle(headStyle, { top: 0 });
  const stickySub: CSSProperties = stickyHeaderStyle(subHeadStyle, { top: row1H });

  return (
    <ScrollableTableContainer
      className="bg-white border"
      style={{ borderColor: LAYOUT_BORDER }}
    >
      <table className="report-wide-matrix min-w-full border-collapse text-[11px] text-black">
        <thead>
          {/* Row 1: standard codes (span sub-cols) + leading/trailing labels */}
          <tr ref={row1Ref}>
            <th rowSpan={2} className="px-2 py-1 text-left align-bottom" style={stickyHead}>
              <SortableHeader column="instructor" label="Classroom Instructors" title="Classroom Instructors" description="Section instructor who taught the student; rows are grouped by this." sortColumn={sortColumn} sortDirection={sortDirection} onClick={onHeaderClick} className="text-white" />
            </th>
            <th rowSpan={2} className="px-2 py-1 text-left align-bottom" style={stickyHead}>
              <SortableHeader column="student" label="Student Name" sortColumn={sortColumn} sortDirection={sortDirection} onClick={onHeaderClick} className="text-white" />
            </th>
            <th rowSpan={2} className="px-2 py-1 align-bottom" style={stickyHead}>
              <SortableHeader column="score" label="Score %" title="Score Percent" description="Student's overall year-to-date percent score across all standards." sortColumn={sortColumn} sortDirection={sortDirection} onClick={onHeaderClick} align="center" className="text-white" />
            </th>
            {showTestsTaken && (
              <th rowSpan={2} className="px-2 py-1 align-bottom" style={stickyHead}>
                <SortableHeader column="tests_taken" label="Tests Taken" title="Tests Taken" description="Count of assessments the student has taken year-to-date." sortColumn={sortColumn} sortDirection={sortDirection} onClick={onHeaderClick} align="center" className="text-white" />
              </th>
            )}
            {standards.map((s) => {
              const hasUnits = showUnitNames && s.unit_count > 0;
              return (
                <th
                  key={s.standard_label}
                  colSpan={subCols}
                  className={`px-2 py-1 text-center${hasUnits ? ' cursor-help' : ''}`}
                  style={stickyHead}
                  // Full assessment list on hover (screen) — the wall of text is
                  // collapsed to a count on screen and expanded in print.
                  title={hasUnits ? s.unit_names : undefined}
                >
                  <div>{s.standard_label}</div>
                  {hasUnits && (
                    <>
                      {/* Compact affordance shown everywhere: how many
                          assessments fed this standard. Keeps the header
                          readable instead of a wall of text; the full list is
                          in the hover tooltip and (in print) the row below. */}
                      <div className="text-[9px] font-normal leading-tight opacity-80">
                        {s.unit_count} assessment{s.unit_count === 1 ? '' : 's'}
                      </div>
                      {/* Full unit names — print/PDF only, so the paginated
                          export keeps variant 3's per-standard assessment
                          detail. Hidden on screen (collapsed to the count). */}
                      <div className="hidden print:block text-[9px] font-normal leading-tight opacity-90">
                        {s.unit_names}
                      </div>
                    </>
                  )}
                </th>
              );
            })}
            <th rowSpan={2} className="px-2 py-1 align-bottom" style={stickyHead}>
              <SortableHeader column="points_possible" label="Possible Points" title="Possible Points" description="Maximum points obtainable across all standards year-to-date." sortColumn={sortColumn} sortDirection={sortDirection} onClick={onHeaderClick} align="center" className="text-white" />
            </th>
            <th rowSpan={2} className="px-2 py-1 align-bottom" style={stickyHead}>
              <SortableHeader column="points_received" label="# Correct Answers" title="Number of Correct Answers" description="Total points received across all standards year-to-date." sortColumn={sortColumn} sortDirection={sortDirection} onClick={onHeaderClick} align="center" className="text-white" />
            </th>
          </tr>
          {/* Row 2: per-standard Score / % sub-headers */}
          <tr>
            {standards.map((s) =>
              showScore ? (
                [
                  <th key={`${s.standard_label}-score`} className="px-2 py-0.5" style={stickySub}>
                    Score
                  </th>,
                  <th key={`${s.standard_label}-pct`} className="px-2 py-0.5" style={stickySub}>
                    %
                  </th>,
                ]
              ) : (
                <th key={`${s.standard_label}-pct`} className="px-2 py-0.5" style={stickySub}>
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
    </ScrollableTableContainer>
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

      {students.map((st) => {
        // Legacy bands the Student Name / Score% / Tests-Taken cells on the
        // student's overall mastery Score% (RDL Textbox…BackgroundColor).
        const stBg = qsrPerformanceColor(st.score_pct);
        return (
          <tr key={st.user_uid}>
            <td className="px-2 py-1" style={{ border }} />
            <td
              className="px-2 py-1 whitespace-nowrap"
              style={{ border, backgroundColor: stBg }}
            >
              {st.user_name}
            </td>
            <td className="px-2 py-1 text-center" style={{ border, backgroundColor: stBg }}>
              {fmtPct(st.score_pct)}
            </td>
            {showTestsTaken && (
              <td className="px-2 py-1 text-center" style={{ border, backgroundColor: stBg }}>
                {st.tests_taken}
              </td>
            )}
            {standards.map((s) => {
              const cell = st.cells[s.standard_label];
              // Per-standard "%" bands on its own mastery value; the Score
              // "n/N" cell uses the neutral legacy grey. No-data → "-", white
              // (unfilled), per RDL IsNothing(Possible_Points).
              const pctBg = cell ? qsrPerformanceColor(cell.score_pct) : undefined;
              if (showScore) {
                return [
                  <td
                    key={`${s.standard_label}-sc`}
                    className="px-2 py-1 text-center"
                    style={{ border, backgroundColor: cell ? QSR_POINTS_GREY : undefined }}
                  >
                    {cell ? fmtScore(cell) : '-'}
                  </td>,
                  <td
                    key={`${s.standard_label}-pc`}
                    className="px-2 py-1 text-center"
                    style={{ border, backgroundColor: pctBg }}
                  >
                    {cell ? fmtPct(cell.score_pct) : '-'}
                  </td>,
                ];
              }
              return (
                <td
                  key={`${s.standard_label}-pc`}
                  className="px-2 py-1 text-center"
                  style={{ border, backgroundColor: pctBg }}
                >
                  {cell ? fmtPct(cell.score_pct) : '-'}
                </td>
              );
            })}
            <td
              className="px-2 py-1 text-center"
              style={{ border, backgroundColor: QSR_POINTS_GREY }}
            >
              {fmtPts(st.points_possible)}
            </td>
            <td
              className="px-2 py-1 text-center"
              style={{ border, backgroundColor: QSR_POINTS_GREY }}
            >
              {fmtPts(st.points_received)}
            </td>
          </tr>
        );
      })}

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
  let bg: string | undefined;
  if (total) {
    if (kind === 'pct') {
      value = fmtPct(total.score_pct);
      // Subtotal/grand Score% bands on mastery (RDL Textbox69/Textbox84).
      bg = qsrPerformanceColor(total.score_pct);
    } else if (kind === 'received') {
      value = fmtPts(total.points_received);
      bg = QSR_POINTS_GREY;
    } else {
      value = fmtPts(total.points_possible);
      bg = QSR_POINTS_GREY;
    }
  }
  return (
    <>
      <td
        className="px-2 py-1 text-center font-semibold"
        style={{ border, backgroundColor: bg }}
      >
        {value}
      </td>
      {showScore && <td className="px-2 py-1" style={{ border }} />}
    </>
  );
}
