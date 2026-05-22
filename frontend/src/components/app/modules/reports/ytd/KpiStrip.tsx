import type { YTDKpis } from '@/lib/reports/types';
import KpiCard from '@/components/app/modules/reports/shared/KpiCard';

function formatNumber(n: number): string {
  return n.toLocaleString(undefined, { maximumFractionDigits: 0 });
}

export default function KpiStrip({ kpis }: { kpis: YTDKpis }) {
  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-2 w-full h-full">
      <KpiCard
        label="Total Questions"
        value={formatNumber(kpis.total_questions)}
      />
      <KpiCard
        label="Total Students"
        value={formatNumber(kpis.total_students)}
      />
      <KpiCard
        label="Score"
        value={formatNumber(kpis.total_points_earned)}
      />
      <KpiCard
        label="Points Possible"
        value={formatNumber(kpis.total_points_possible)}
      />
      <KpiCard label="% Correct" value={kpis.overall_avg_pct} />
    </div>
  );
}
