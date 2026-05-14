import type { StandardSummaryKpis } from '@/lib/reports/types';
import KpiCard from '@/components/app/modules/reports/shared/KpiCard';

const CARD_CLASSNAME = 'min-h-[100px]';
const VALUE_CLASSNAME = 'text-[24px]';

interface KpiStripProps {
  kpis: StandardSummaryKpis;
}

export default function KpiStrip({ kpis }: KpiStripProps) {
  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-2 w-full h-full">
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
        label="Total Students"
        value={String(kpis.total_students)}
      />
      <KpiCard
        className={CARD_CLASSNAME}
        valueClassName={VALUE_CLASSNAME}
        label="At-Target (≥80%)"
        value={kpis.at_target_pct_str}
      />
      <KpiCard
        className={CARD_CLASSNAME}
        valueClassName={VALUE_CLASSNAME}
        label="Grade Average"
        value={kpis.grade_average_pct}
      />
    </div>
  );
}
