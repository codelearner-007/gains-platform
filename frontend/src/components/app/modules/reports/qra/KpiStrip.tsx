import type { KPIs } from '@/lib/reports/types';
import KpiCard from '@/components/app/modules/reports/shared/KpiCard';

export default function KpiStrip({ kpis }: { kpis: KPIs }) {
  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-2 w-full h-full">
      <KpiCard label="Total Students" value={String(kpis.total_students)} />
      <KpiCard label="Number of Questions" value={String(kpis.total_questions)} />
      <KpiCard label="Number of Standards" value={String(kpis.total_standards)} />
      <KpiCard label="Grade Average" value={kpis.grade_average_pct} />
      <KpiCard label="Overall Highest %" value={kpis.grade_max_pct} />
      <KpiCard label="Overall Lowest %" value={kpis.grade_min_pct} />
    </div>
  );
}
