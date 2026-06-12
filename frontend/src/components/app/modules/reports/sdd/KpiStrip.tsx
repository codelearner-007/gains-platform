import type { SddKpis } from '@/lib/reports/types';
import SharedKpiStrip from '@/components/app/modules/reports/shared/KpiStrip';
import InstructorsValue from '@/components/app/modules/reports/shared/InstructorsValue';

const SDD_VALUE_CLASSNAME = 'text-[24px]';

interface KpiStripProps {
  kpis: SddKpis;
}

/**
 * SDD KPI strip — five tiles: Instructor + four measures.
 * Responsive: 1 col on phone, 2 cols on sm, 3 cols on md, 5 cols on lg.
 * Putting Instructor INTO the KPI row keeps the strand panel below
 * full-width (matches the Schoology PowerBI dashboard).
 */
export default function KpiStrip({ kpis }: KpiStripProps) {
  return (
    <SharedKpiStrip
      cols={5}
      tiles={[
        {
          label: 'Instructor(s)',
          valueClassName: 'text-[14px]',
          value: <InstructorsValue instructors={kpis.instructors} />,
        },
        {
          label: 'Total Students',
          valueClassName: SDD_VALUE_CLASSNAME,
          value: String(kpis.total_students),
        },
        {
          label: 'Number of Questions',
          valueClassName: SDD_VALUE_CLASSNAME,
          value: String(kpis.total_questions),
        },
        {
          label: 'Number of Standards',
          valueClassName: SDD_VALUE_CLASSNAME,
          value: String(kpis.total_standards),
        },
        {
          label: 'Grade Average',
          valueClassName: SDD_VALUE_CLASSNAME,
          value: kpis.grade_average_pct,
        },
      ]}
    />
  );
}
