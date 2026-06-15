import type { IadKpis } from '@/lib/reports/types';
import SharedKpiStrip from '@/components/app/modules/reports/shared/KpiStrip';
import { formatAnswerHtml } from '@/lib/reports/format';
import RichReportHtml from '../shared/RichReportHtml';

const IAD_VALUE_CLASSNAME = 'text-[24px]';

interface Props {
  kpis: IadKpis;
}

function TopWrongValue({
  answer,
  count,
  pct,
}: {
  answer: string;
  count: number;
  pct: string;
}) {
  if (!answer) {
    return (
      <div className="text-[16px] font-bold text-black text-center">—</div>
    );
  }
  return (
    <div className="flex flex-col items-center justify-center gap-0.5 leading-tight px-1">
      <div className="text-[16px] font-bold text-black text-center max-w-full overflow-hidden">
        <RichReportHtml
          className="pilot-answer-html"
          html={formatAnswerHtml(answer, 'most common wrong answer')}
        />
      </div>
      <div className="text-[11px] text-neutral-700 font-medium">
        {count} {count === 1 ? 'student' : 'students'} · {pct}
      </div>
    </div>
  );
}

export default function KpiStrip({ kpis }: Props) {
  return (
    <SharedKpiStrip
      cols={6}
      tiles={[
        {
          label: 'Total Students',
          valueClassName: IAD_VALUE_CLASSNAME,
          value: String(kpis.total_attempts),
        },
        {
          label: 'Got it Right',
          valueClassName: IAD_VALUE_CLASSNAME,
          value: (
            <div className="flex flex-col items-center leading-tight">
              <div className="text-[24px] font-bold text-black">
                {kpis.correct_count}
              </div>
              <div className="text-[12px] text-neutral-700 mt-0.5">
                {kpis.correct_pct}
              </div>
            </div>
          ),
        },
        {
          label: 'Got it Wrong',
          valueClassName: IAD_VALUE_CLASSNAME,
          value: (
            <div className="flex flex-col items-center leading-tight">
              <div className="text-[24px] font-bold text-black">
                {kpis.incorrect_count}
              </div>
              <div className="text-[12px] text-neutral-700 mt-0.5">
                {kpis.incorrect_pct}
              </div>
            </div>
          ),
        },
        {
          label: 'Distinct Answers',
          valueClassName: IAD_VALUE_CLASSNAME,
          value: String(kpis.distinct_answers),
        },
        {
          label: 'Total Incorrect Choices',
          valueClassName: IAD_VALUE_CLASSNAME,
          value: String(kpis.total_incorrect_choices),
        },
        {
          label: 'Most Common Wrong',
          valueClassName: 'text-[14px]',
          value: (
            <TopWrongValue
              answer={kpis.top_wrong_answer}
              count={kpis.top_wrong_count}
              pct={kpis.top_wrong_pct}
            />
          ),
        },
      ]}
    />
  );
}
