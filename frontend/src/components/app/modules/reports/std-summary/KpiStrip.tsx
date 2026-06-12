import type { StandardSummaryKpis } from '@/lib/reports/types';
import SharedKpiStrip from '@/components/app/modules/reports/shared/KpiStrip';

const VALUE_CLASSNAME = 'text-[24px]';

interface KpiStripProps {
  kpis: StandardSummaryKpis;
}

export default function KpiStrip({ kpis }: KpiStripProps) {
  return (
    <SharedKpiStrip
      cols={5}
      tiles={[
        {
          label: 'Total Standards',
          valueClassName: VALUE_CLASSNAME,
          value: String(kpis.total_standards),
        },
        {
          label: 'Total Questions',
          valueClassName: VALUE_CLASSNAME,
          value: String(kpis.total_questions),
        },
        {
          label: 'Total Students',
          valueClassName: VALUE_CLASSNAME,
          value: String(kpis.total_students),
        },
        {
          label: 'At-Target (≥80%)',
          valueClassName: VALUE_CLASSNAME,
          value: kpis.at_target_pct_str,
        },
        {
          label: 'Grade Average',
          valueClassName: VALUE_CLASSNAME,
          value: kpis.grade_average_pct,
        },
      ]}
    />
  );
}
