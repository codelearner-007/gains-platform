import type { IadKpis } from '@/lib/reports/types';
import KpiCard from '@/components/app/modules/reports/shared/KpiCard';

const IAD_CARD_CLASSNAME = 'min-h-[100px]';
const IAD_VALUE_CLASSNAME = 'text-[24px]';

interface Props {
  kpis: IadKpis;
}

/**
 * Per-question KPI strip — replicates the pivotTable + multiRowCard
 * cluster (visuals #3, #5, #11, #12) from the PBIX IAD page but
 * presented as five compact KPI cards.
 */
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
    <div className="flex flex-col items-center justify-center gap-0.5 leading-tight">
      <div className="text-[20px] font-bold text-black">{count}</div>
      <div className="text-[10px] text-neutral-700 text-center px-1 leading-tight line-clamp-2">
        {answer}
      </div>
      <div className="text-[11px] font-semibold text-black mt-0.5">{pct}</div>
    </div>
  );
}

export default function KpiStrip({ kpis }: Props) {
  return (
    <div className="grid grid-cols-5 gap-2 w-full h-full">
      <KpiCard
        className={IAD_CARD_CLASSNAME}
        valueClassName={IAD_VALUE_CLASSNAME}
        label="Total Students"
        value={String(kpis.total_attempts)}
      />
      <KpiCard
        className={IAD_CARD_CLASSNAME}
        valueClassName={IAD_VALUE_CLASSNAME}
        label="Got it Right"
        value={
          <div className="flex flex-col items-center leading-tight">
            <div className="text-[24px] font-bold text-black">
              {kpis.correct_count}
            </div>
            <div className="text-[12px] text-neutral-700 mt-0.5">
              {kpis.correct_pct}
            </div>
          </div>
        }
      />
      <KpiCard
        className={IAD_CARD_CLASSNAME}
        valueClassName={IAD_VALUE_CLASSNAME}
        label="Got it Wrong"
        value={
          <div className="flex flex-col items-center leading-tight">
            <div className="text-[24px] font-bold text-black">
              {kpis.incorrect_count}
            </div>
            <div className="text-[12px] text-neutral-700 mt-0.5">
              {kpis.incorrect_pct}
            </div>
          </div>
        }
      />
      <KpiCard
        className={IAD_CARD_CLASSNAME}
        valueClassName={IAD_VALUE_CLASSNAME}
        label="Distinct Answers"
        value={String(kpis.distinct_answers)}
      />
      <KpiCard
        className={IAD_CARD_CLASSNAME}
        valueClassName="text-[14px]"
        label="Most Common Wrong"
        value={
          <TopWrongValue
            answer={kpis.top_wrong_answer}
            count={kpis.top_wrong_count}
            pct={kpis.top_wrong_pct}
          />
        }
      />
    </div>
  );
}
