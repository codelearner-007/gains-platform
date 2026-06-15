import type { KPIs } from '@/lib/reports/types';
import SharedKpiStrip from '@/components/app/modules/reports/shared/KpiStrip';
import InstructorsValue from '@/components/app/modules/reports/shared/InstructorsValue';

const VALUE_CLASSNAME = 'text-[22px]';

/**
 * QRA KPI strip — seven tiles: Instructor + six measures.
 * Responsive grid: 1 col phone, 2 cols sm, 4 cols md, 7 cols xl.
 * The Instructor card lives inside the strip so the Summary-by-Standards
 * section below renders full-width.
 */
export default function KpiStrip({ kpis }: { kpis: KPIs }) {
  return (
    <SharedKpiStrip
      cols={7}
      tiles={[
        {
          label: 'Instructor(s)',
          valueClassName: 'text-[14px]',
          value: <InstructorsValue instructors={kpis.instructors} />,
        },
        {
          label: 'Total Students',
          valueClassName: VALUE_CLASSNAME,
          value: String(kpis.total_students),
        },
        {
          label: 'Number of Questions',
          valueClassName: VALUE_CLASSNAME,
          value: String(kpis.total_questions),
        },
        {
          label: 'Number of Standards',
          valueClassName: VALUE_CLASSNAME,
          value: String(kpis.total_standards),
        },
        {
          label: 'Grade Average',
          valueClassName: VALUE_CLASSNAME,
          value: kpis.grade_average_pct,
        },
        {
          label: 'Overall Highest %',
          valueClassName: VALUE_CLASSNAME,
          value: kpis.grade_max_pct,
        },
        {
          label: 'Overall Lowest %',
          valueClassName: VALUE_CLASSNAME,
          value: kpis.grade_min_pct,
        },
      ]}
    />
  );
}
