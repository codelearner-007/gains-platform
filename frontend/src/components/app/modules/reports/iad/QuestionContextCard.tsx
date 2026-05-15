import type { IadQuestionContext } from '@/lib/reports/types';
import { HEADER_BAR_BG, LAYOUT_BORDER, cellColor } from '@/lib/reports/colors';
import {
  formatCorrectAnswer,
  formatQuestionHtml,
  sanitizeShortAnswer,
} from '@/lib/reports/format';

interface Props {
  question: IadQuestionContext;
}

/**
 * The "selected question" panel — replicates the single-row tableEx
 * (visual #0) on the PBIX IAD page: question number, question text,
 * % correct, correct answer, standards. The right-side colour swatch
 * uses the PBIX traffic-light thresholds (Performance Color).
 */
export default function QuestionContextCard({ question }: Props) {
  const correctLines = formatCorrectAnswer(question.correct_answer).map(
    sanitizeShortAnswer,
  );
  const standards = question.standards || question.strand || '—';
  const pctBg = cellColor(question.grade_average);

  return (
    <div
      className="flex flex-col bg-white border"
      style={{ borderColor: LAYOUT_BORDER }}
    >
      <div
        className="px-3 py-1.5 text-[14px] font-bold text-black"
        style={{ backgroundColor: HEADER_BAR_BG }}
      >
        Selected Question
      </div>
      <div className="grid grid-cols-12 gap-3 p-3">
        <div className="col-span-1 flex flex-col items-center justify-start">
          <div className="text-[11px] uppercase tracking-wide text-neutral-600">
            Question
          </div>
          <div className="text-[28px] font-bold text-black leading-none mt-1">
            {question.question_no}
          </div>
        </div>

        <div className="col-span-6 min-w-0">
          <div className="text-[11px] uppercase tracking-wide text-neutral-600">
            Question
          </div>
          <div
            className="pilot-question-html text-[14px] text-black mt-1 leading-snug"
            dangerouslySetInnerHTML={{
              __html: formatQuestionHtml(question.question),
            }}
          />
        </div>

        <div className="col-span-2 flex flex-col items-start">
          <div className="text-[11px] uppercase tracking-wide text-neutral-600">
            Correct Answer
          </div>
          <div
            className="text-[13px] text-black mt-1 leading-snug"
            style={{ whiteSpace: 'pre-line' }}
          >
            {correctLines.join('\n')}
          </div>
        </div>

        <div className="col-span-1 flex flex-col items-center justify-start">
          <div className="text-[11px] uppercase tracking-wide text-neutral-600">
            % Correct
          </div>
          <div
            className="mt-1 px-2 py-1 rounded text-[16px] font-bold text-black"
            style={{ backgroundColor: pctBg }}
          >
            {question.grade_average_pct}
          </div>
        </div>

        <div className="col-span-2 flex flex-col items-start">
          <div className="text-[11px] uppercase tracking-wide text-neutral-600">
            Standards
          </div>
          <div className="text-[13px] text-black mt-1 leading-snug break-words">
            {standards}
          </div>
        </div>
      </div>

      {question.description ? (
        <div
          className="border-t px-3 py-2 text-[12px] text-neutral-700 leading-snug"
          style={{ borderColor: LAYOUT_BORDER }}
        >
          <span className="font-semibold text-neutral-800">Description: </span>
          {question.description}
        </div>
      ) : null}
    </div>
  );
}
