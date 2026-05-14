import type { StrandSummaryKpis } from '@/lib/reports/types';
import KpiCard from '@/components/app/modules/reports/shared/KpiCard';

const CARD_CLASSNAME = 'min-h-[100px]';
const VALUE_CLASSNAME = 'text-[24px]';

interface KpiStripProps {
  kpis: StrandSummaryKpis;
}

function WorstStrandValue({
  strand,
  pct,
}: {
  strand: string;
  pct: string;
}) {
  if (!strand) return <>—</>;
  return (
    <div className="flex flex-col items-center gap-0.5 leading-tight">
      <div className="text-[14px] font-bold text-black truncate max-w-full px-1">
        {strand}
      </div>
      <div className="text-[18px] font-bold leading-tight">{pct}</div>
    </div>
  );
}

export default function KpiStrip({ kpis }: KpiStripProps) {
  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-2 w-full h-full">
      <KpiCard
        className={CARD_CLASSNAME}
        valueClassName={VALUE_CLASSNAME}
        label="Total Strands"
        value={String(kpis.total_strands)}
      />
      <KpiCard
        className={CARD_CLASSNAME}
        valueClassName={VALUE_CLASSNAME}
        label="Total Standards"
        value={String(kpis.total_standards)}
      />
      <KpiCard
        className={CARD_CLASSNAME}
        valueClassName={VALUE_CLASSNAME}
        label="Total Questions"
        value={String(kpis.total_questions)}
      />
      <KpiCard
        className={CARD_CLASSNAME}
        valueClassName={VALUE_CLASSNAME}
        label="Grade Average"
        value={kpis.grade_average_pct}
      />
      <KpiCard
        className={CARD_CLASSNAME}
        valueClassName="text-[14px]"
        label="Worst Strand"
        value={
          <WorstStrandValue
            strand={kpis.worst_strand}
            pct={kpis.worst_strand_pct}
          />
        }
      />
    </div>
  );
}
