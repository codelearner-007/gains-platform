'use client';

import { useMemo, useState } from 'react';
import { Check, X } from 'lucide-react';
import type { IadStudentAttempt } from '@/lib/reports/types';
import {
  EMPTY_TABLE_FG,
  HEADER_BAR_BG,
  LAYOUT_BORDER,
  IAD_GREEN,
  IAD_RED,
  STATUS_CORRECT_FG,
  STATUS_INCORRECT_FG,
} from '@/lib/reports/colors';
import {
  tableCellStyle as cellBase,
  tableHeaderStyle as headerStyle,
  stickyHeaderStyle,
} from '../shared/tableStyles';
import ScrollableTableContainer from '../shared/ScrollableTableContainer';
import { formatAnswerHtml } from '@/lib/reports/format';
import RichReportHtml from '../shared/RichReportHtml';
import { SortableHeader, useTableSort } from '@/lib/reports/useTableSort';

interface Props {
  attempts: IadStudentAttempt[];
  /**
   * False for cube-only (parquet-loaded) schools that have no
   * fact_student_submission rows. The KPI strip / distractor breakdown on the
   * rest of the page are still cube-derived, so we render an explicit note in
   * place of the per-student table instead of an empty "no attempts" grid.
   */
  perStudentAvailable?: boolean;
}

type StudentSortKey =
  | 'user_name'
  | 'answer_submission'
  | 'is_correct'
  | 'points_received'
  | 'score_pct'
  | 'latest_attempt';

type AttemptScope = 'wrong' | 'all';

const STUDENT_SORT_ACCESSORS: Record<
  StudentSortKey,
  (a: IadStudentAttempt) => string | number | null
> = {
  user_name: (a) => (a.user_name || '').toLowerCase(),
  answer_submission: (a) => (a.answer_submission || '').toLowerCase(),
  is_correct: (a) => (a.is_correct ? 1 : 0),
  points_received: (a) => a.points_received,
  score_pct: (a) => a.score_pct,
  latest_attempt: (a) => a.latest_attempt || null,
};

const STUDENT_INITIAL_DIRECTIONS: Partial<
  Record<StudentSortKey, 'asc' | 'desc'>
> = {
  points_received: 'desc',
  score_pct: 'desc',
  latest_attempt: 'desc',
};

const dateFmt = new Intl.DateTimeFormat('en-US', {
  month: 'short',
  day: 'numeric',
  hour: 'numeric',
  minute: '2-digit',
});

function formatDate(iso: string): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '—';
  return dateFmt.format(d);
}

export default function StudentAttemptTable({
  attempts,
  perStudentAvailable = true,
}: Props) {
  // Legacy PBIX default: wrong-only (Points_Received = '0').
  const [scope, setScope] = useState<AttemptScope>('wrong');
  const wrong = useMemo(
    () => attempts.filter((a) => !a.is_correct),
    [attempts],
  );
  const scoped = scope === 'wrong' ? wrong : attempts;

  const { sortedRows: filtered, sortColumn, sortDirection, onHeaderClick } =
    useTableSort<IadStudentAttempt, StudentSortKey>({
      rows: scoped,
      accessors: STUDENT_SORT_ACCESSORS,
      defaultColumn: 'user_name',
      defaultDirection: 'asc',
      initialDirections: STUDENT_INITIAL_DIRECTIONS,
    });

  // Cube-only (parquet-loaded) schools have no per-student fact rows. The KPI
  // strip + distractor breakdown above are still cube-derived, so we show an
  // explicit note here instead of a misleading empty per-attempt grid.
  if (!perStudentAvailable) {
    return (
      <div
        className="flex flex-col bg-white border"
        style={{ borderColor: LAYOUT_BORDER }}
      >
        <div
          className="px-3 py-1.5"
          style={{ backgroundColor: HEADER_BAR_BG }}
        >
          <span className="text-[14px] font-bold text-black">
            Per-Student Attempts
          </span>
        </div>
        <p className="px-3 py-3 text-[12px]" style={{ color: EMPTY_TABLE_FG }}>
          Per-student detail isn&rsquo;t available for this school — showing
          assessment-level totals from the cube.
        </p>
      </div>
    );
  }

  return (
    <div
      className="flex flex-col bg-white border"
      style={{ borderColor: LAYOUT_BORDER }}
    >
      <div
        className="px-3 py-1.5 flex items-center justify-between gap-2"
        style={{ backgroundColor: HEADER_BAR_BG }}
      >
        <span className="text-[14px] font-bold text-black">
          Per-Student Attempts
        </span>
        <div
          className="flex rounded-sm overflow-hidden border text-[11px] font-semibold print:hidden"
          style={{ borderColor: LAYOUT_BORDER }}
          role="tablist"
          aria-label="Filter student attempts"
        >
          <button
            type="button"
            role="tab"
            aria-selected={scope === 'wrong'}
            onClick={() => setScope('wrong')}
            className={`px-2 py-0.5 transition-colors ${
              scope === 'wrong'
                ? 'bg-black text-white'
                : 'bg-white text-black hover:bg-neutral-100'
            }`}
          >
            Wrong only ({wrong.length})
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={scope === 'all'}
            onClick={() => setScope('all')}
            className={`px-2 py-0.5 transition-colors ${
              scope === 'all'
                ? 'bg-black text-white'
                : 'bg-white text-black hover:bg-neutral-100'
            }`}
          >
            All ({attempts.length})
          </button>
        </div>
      </div>
      <ScrollableTableContainer>
        <table
          style={{
            borderCollapse: 'collapse',
            width: '100%',
            tableLayout: 'fixed',
          }}
        >
          <colgroup>
            <col style={{ width: '20%' }} />
            <col style={{ width: '38%' }} />
            <col style={{ width: '8%' }} />
            <col style={{ width: '12%' }} />
            <col style={{ width: '10%' }} />
            <col style={{ width: '12%' }} />
          </colgroup>
          <thead>
            <tr>
              <th style={stickyHeaderStyle(headerStyle, { top: 0 })}>
                <SortableHeader
                  column="user_name"
                  label="Student"
                  sortColumn={sortColumn}
                  sortDirection={sortDirection}
                  onClick={onHeaderClick}
                />
              </th>
              <th style={stickyHeaderStyle(headerStyle, { top: 0 })}>
                <SortableHeader
                  column="answer_submission"
                  label="Their Answer"
                  sortColumn={sortColumn}
                  sortDirection={sortDirection}
                  onClick={onHeaderClick}
                />
              </th>
              <th style={stickyHeaderStyle({ ...headerStyle, textAlign: 'center' }, { top: 0 })}>
                <SortableHeader
                  column="is_correct"
                  label="Correct?"
                  title="Correct?"
                  description="Whether the student's answer was correct or incorrect."
                  sortColumn={sortColumn}
                  sortDirection={sortDirection}
                  onClick={onHeaderClick}
                  align="center"
                />
              </th>
              <th style={stickyHeaderStyle({ ...headerStyle, textAlign: 'right' }, { top: 0 })}>
                <SortableHeader
                  column="points_received"
                  label="Points"
                  title="Points Received / Points Possible"
                  description="Points the student earned out of points possible on this question."
                  sortColumn={sortColumn}
                  sortDirection={sortDirection}
                  onClick={onHeaderClick}
                  align="right"
                />
              </th>
              <th style={stickyHeaderStyle({ ...headerStyle, textAlign: 'right' }, { top: 0 })}>
                <SortableHeader
                  column="score_pct"
                  label="Score %"
                  title="Score Percentage"
                  description="The student's score on this question as a percentage of points possible."
                  sortColumn={sortColumn}
                  sortDirection={sortDirection}
                  onClick={onHeaderClick}
                  align="right"
                />
              </th>
              <th style={stickyHeaderStyle(headerStyle, { top: 0 })}>
                <SortableHeader
                  column="latest_attempt"
                  label="Submitted"
                  title="Submitted"
                  description="Date and time of the student's latest attempt."
                  sortColumn={sortColumn}
                  sortDirection={sortDirection}
                  onClick={onHeaderClick}
                />
              </th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((a, idx) => (
              // user_uid is per-student; a single student can have multiple
              // attempts on the same question, so composite-key on idx too.
              <tr key={`${a.user_uid}-${idx}`} className="hover:bg-neutral-50">
                <td style={{ ...cellBase, fontWeight: 600 }}>{a.user_name}</td>
                <td
                  style={{
                    ...cellBase,
                    whiteSpace: 'normal',
                    wordBreak: 'break-word',
                  }}
                >
                  {a.answer_submission ? (
                    <RichReportHtml
                      className="pilot-answer-html"
                      html={formatAnswerHtml(a.answer_submission, 'student answer')}
                    />
                  ) : (
                    '—'
                  )}
                </td>
                {/* Binary green/red on is_correct. Legacy's per-cell rule is
                    3-band on partial-credit Points_Received, but that grain
                    isn't surfaced at this per-attempt level — intentional
                    divergence (MASTER_PLAN §6, IAD-PALETTE-2). */}
                <td
                  style={{
                    ...cellBase,
                    textAlign: 'center',
                    backgroundColor: a.is_correct ? IAD_GREEN : IAD_RED,
                  }}
                >
                  {a.is_correct ? (
                    <Check
                      className="inline h-3.5 w-3.5"
                      style={{ color: STATUS_CORRECT_FG }}
                      aria-label="correct"
                    />
                  ) : (
                    <X
                      className="inline h-3.5 w-3.5"
                      style={{ color: STATUS_INCORRECT_FG }}
                      aria-label="incorrect"
                    />
                  )}
                </td>
                <td
                  style={{
                    ...cellBase,
                    textAlign: 'right',
                    fontVariantNumeric: 'tabular-nums',
                  }}
                >
                  {a.points_received.toFixed(2)} / {a.points_possible.toFixed(2)}
                </td>
                <td
                  style={{
                    ...cellBase,
                    textAlign: 'right',
                    fontVariantNumeric: 'tabular-nums',
                  }}
                >
                  {(a.score_pct * 100).toFixed(0)}%
                </td>
                <td style={cellBase}>{formatDate(a.latest_attempt)}</td>
              </tr>
            ))}
            {filtered.length === 0 && (
              <tr>
                <td
                  colSpan={6}
                  style={{
                    ...cellBase,
                    textAlign: 'center',
                    color: EMPTY_TABLE_FG,
                  }}
                >
                  No student attempts in this view.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </ScrollableTableContainer>
    </div>
  );
}
