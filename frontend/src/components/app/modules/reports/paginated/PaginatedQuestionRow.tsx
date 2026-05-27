import { Fragment } from 'react';
import type { PaginatedQuestionRow as Row } from '@/lib/reports/types';
import { LAYOUT_BORDER, performanceColor } from '@/lib/reports/colors';
import {
  formatAnswerHtml,
  formatCorrectAnswer,
  formatQuestionHtml,
  splitStandards,
} from '@/lib/reports/format';
import RichReportHtml from '../shared/RichReportHtml';

interface Props {
  row: Row;
  /** Render the Standards column (ord 11 only — ord 12/13 group by it). */
  showStandardsColumn?: boolean;
  /** Render the Students-with-Incorrect-Choice column (ord 11). */
  showStudentsColumn?: boolean;
}

/**
 * Cells (NOT a `<tr>`) shared by every QRA paginated table variant. Mirrors
 * the existing interactive QRA cell formatting (RichReportHtml +
 * formatQuestionHtml / formatAnswerHtml / splitStandards) so the same
 * Schoology answer HTML, LaTeX images, and embedded URLs render identically
 * across all six reports. The caller wraps these in its own `<tr>` and is
 * responsible for any variant-specific trailing cells.
 */
export default function PaginatedQuestionRowCells({
  row,
  showStandardsColumn = false,
  showStudentsColumn = false,
}: Props) {
  const correctHtml = formatCorrectAnswer(row.correct_answer)
    .map((line) => formatAnswerHtml(line, 'correct answer'))
    .join('<br />');

  const choicesRaw = (row.incorrect_choice_details || '').replace(
    /\], (?=\d+\.?\d*% chose \[)/g,
    ']\n',
  );
  const choicesHtml =
    row.grade_average >= 1 ? '' : formatAnswerHtml(choicesRaw, 'incorrect choice');

  const namesRaw = (row.incorrect_details_name || '').replace(
    /\], (?=\[)/g,
    ']\n',
  );
  const namesHtml =
    row.grade_average >= 1 ? '' : formatAnswerHtml(namesRaw, 'incorrect choice');

  const standards = splitStandards(row.standards);

  return (
    <Fragment>
      <td
        className="border-r px-2 py-1 text-right tabular-nums font-semibold w-[44px]"
        style={{ borderColor: LAYOUT_BORDER }}
      >
        {row.question_no}
      </td>
      <td
        className="border-r px-2 py-1 leading-snug"
        style={{ borderColor: LAYOUT_BORDER, overflowWrap: 'anywhere' }}
      >
        <RichReportHtml
          className="pilot-question-html"
          html={formatQuestionHtml(row.question)}
        />
      </td>
      {showStandardsColumn && (
        <td
          className="border-r px-2 py-1 font-mono text-[10px] w-[140px] break-all"
          style={{ borderColor: LAYOUT_BORDER }}
        >
          {standards.length > 0
            ? standards.map((s, i) => (
                <div key={`${row.question_id}-std-${i}`}>{s}</div>
              ))
            : '—'}
        </td>
      )}
      <td
        className="border-r px-2 py-1 text-right tabular-nums font-semibold w-[80px]"
        style={{
          borderColor: LAYOUT_BORDER,
          backgroundColor: performanceColor(row.grade_average),
        }}
      >
        {row.grade_average_pct}
      </td>
      <td
        className="border-r px-2 py-1 w-[160px]"
        style={{ borderColor: LAYOUT_BORDER, overflowWrap: 'anywhere' }}
      >
        <RichReportHtml className="pilot-answer-html" html={correctHtml} />
      </td>
      <td
        className="border-r px-2 py-1 text-[10px]"
        style={{ borderColor: LAYOUT_BORDER, overflowWrap: 'anywhere' }}
      >
        {choicesHtml ? (
          <RichReportHtml className="pilot-answer-html" html={choicesHtml} />
        ) : (
          '—'
        )}
      </td>
      {showStudentsColumn && (
        <td
          className="px-2 py-1 text-[10px] w-[220px]"
          style={{ borderColor: LAYOUT_BORDER, overflowWrap: 'anywhere' }}
        >
          {namesHtml ? (
            <RichReportHtml className="pilot-answer-html" html={namesHtml} />
          ) : (
            '—'
          )}
        </td>
      )}
    </Fragment>
  );
}
