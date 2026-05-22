'use client';

import { useMemo } from 'react';
import { Check, X } from 'lucide-react';
import type { IadStudentAttempt } from '@/lib/reports/types';
import {
  EMPTY_TABLE_FG,
  HEADER_BAR_BG,
  LAYOUT_BORDER,
  PERF_GREEN,
  PERF_PINK,
  STATUS_CORRECT_FG,
  STATUS_INCORRECT_FG,
} from '@/lib/reports/colors';
import {
  tableCellStyle as cellBase,
  tableHeaderStyle as headerStyle,
} from '../shared/tableStyles';
import { formatAnswerHtml } from '@/lib/reports/format';
import RichReportHtml from '../shared/RichReportHtml';

interface Props {
  attempts: IadStudentAttempt[];
}

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

export default function StudentAttemptTable({ attempts }: Props) {
  const filtered = useMemo(
    () =>
      [...attempts].sort((a, b) => a.user_name.localeCompare(b.user_name)),
    [attempts],
  );

  return (
    <div
      className="flex flex-col bg-white border"
      style={{ borderColor: LAYOUT_BORDER }}
    >
      <div
        className="px-3 py-1.5 text-[14px] font-bold text-black"
        style={{ backgroundColor: HEADER_BAR_BG }}
      >
        Per-Student Attempts
      </div>
      <div className="w-full overflow-auto">
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
              <th style={headerStyle}>Student</th>
              <th style={headerStyle}>Their Answer</th>
              <th style={{ ...headerStyle, textAlign: 'center' }}>Correct?</th>
              <th style={{ ...headerStyle, textAlign: 'right' }}>Points</th>
              <th style={{ ...headerStyle, textAlign: 'right' }}>Score %</th>
              <th style={headerStyle}>Submitted</th>
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
                <td
                  style={{
                    ...cellBase,
                    textAlign: 'center',
                    backgroundColor: a.is_correct ? PERF_GREEN : PERF_PINK,
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
      </div>
    </div>
  );
}
