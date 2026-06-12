import type { StrandSummaryKpis } from '@/lib/reports/types';
import SharedKpiStrip from '@/components/app/modules/reports/shared/KpiStrip';

const VALUE_CLASSNAME = 'text-[22px]';

interface KpiStripProps {
  kpis: StrandSummaryKpis;
}

export default function KpiStrip({ kpis }: KpiStripProps) {
  return (
    <SharedKpiStrip
      cols={6}
      tiles={[
        {
          label: 'Total Strands',
          valueClassName: VALUE_CLASSNAME,
          value: String(kpis.total_strands),
        },
        {
          label: 'Total Standards',
          valueClassName: VALUE_CLASSNAME,
          value: String(kpis.total_standards),
        },
        {
          label: 'Total Questions',
          valueClassName: VALUE_CLASSNAME,
          value: kpis.total_questions.toLocaleString(),
        },
        {
          label: 'Total Assessments',
          valueClassName: VALUE_CLASSNAME,
          value: String(kpis.total_assessments),
        },
        {
          label: 'Total Students',
          valueClassName: VALUE_CLASSNAME,
          value: String(kpis.total_students),
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
