import type { StrandSummaryKpis } from '@/lib/reports/types';
import KpiCard from '@/components/app/modules/reports/shared/KpiCard';

const CARD_CLASSNAME = 'min-h-[100px]';
const VALUE_CLASSNAME = 'text-[22px]';

interface KpiStripProps {
  kpis: StrandSummaryKpis;
}

export default function KpiStrip({ kpis }: KpiStripProps) {
  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-2 w-full h-full">
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
        value={kpis.total_questions.toLocaleString()}
      />
      <KpiCard
        className={CARD_CLASSNAME}
        valueClassName={VALUE_CLASSNAME}
        label="Total Assessments"
        value={String(kpis.total_assessments)}
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
        label="Grade Average"
        value={kpis.grade_average_pct}
      />
    </div>
  );
}
