import type { YTDKpis } from '@/lib/reports/types';
import KpiCard from '@/components/app/modules/reports/shared/KpiCard';

export default function KpiStrip({ kpis }: { kpis: YTDKpis }) {
  return (
    <div className="grid grid-cols-6 gap-2 w-full h-full">
      <KpiCard label="Total Students" value={String(kpis.total_students)} />
      <KpiCard
        label="Total Assessments"
        value={String(kpis.total_assessments)}
      />
      <KpiCard label="Avg Score" value={kpis.overall_avg_pct} />
      <KpiCard
        label="Students Improving"
        value={String(kpis.students_improving)}
      />
      <KpiCard
        label="Students Declining"
        value={String(kpis.students_declining)}
      />
      <KpiCard
        label="Total Q's Answered"
        value={kpis.total_questions_answered.toLocaleString()}
      />
    </div>
  );
}
