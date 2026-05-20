import type { SddKpis } from '@/lib/reports/types';
import KpiCard from '@/components/app/modules/reports/shared/KpiCard';

const SDD_CARD_CLASSNAME = 'min-h-[100px]';
const SDD_VALUE_CLASSNAME = 'text-[24px]';

interface KpiStripProps {
  kpis: SddKpis;
}

function InstructorsValue({ instructors }: { instructors: string[] }) {
  const list = instructors.length > 0 ? instructors : ['—'];
  return (
    <div className="flex flex-col items-center justify-center gap-0.5 leading-tight">
      {list.map((name, i) => (
        <div
          key={i}
          className="text-[13px] font-bold text-black text-center leading-tight"
        >
          {name}
        </div>
      ))}
    </div>
  );
}

/**
 * SDD KPI strip — five tiles: Instructor + four measures.
 * Responsive: 1 col on phone, 2 cols on sm, 3 cols on md, 5 cols on lg.
 * Putting Instructor INTO the KPI row keeps the strand panel below
 * full-width (matches the Schoology PowerBI dashboard).
 */
export default function KpiStrip({ kpis }: KpiStripProps) {
  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-2 w-full h-full">
      <KpiCard
        className={SDD_CARD_CLASSNAME}
        valueClassName="text-[14px]"
        label="Instructor(s)"
        value={<InstructorsValue instructors={kpis.instructors} />}
      />
      <KpiCard
        className={SDD_CARD_CLASSNAME}
        valueClassName={SDD_VALUE_CLASSNAME}
        label="Total Students"
        value={String(kpis.total_students)}
      />
      <KpiCard
        className={SDD_CARD_CLASSNAME}
        valueClassName={SDD_VALUE_CLASSNAME}
        label="Number of Questions"
        value={String(kpis.total_questions)}
      />
      <KpiCard
        className={SDD_CARD_CLASSNAME}
        valueClassName={SDD_VALUE_CLASSNAME}
        label="Number of Standards"
        value={String(kpis.total_standards)}
      />
      <KpiCard
        className={SDD_CARD_CLASSNAME}
        valueClassName={SDD_VALUE_CLASSNAME}
        label="Grade Average"
        value={kpis.grade_average_pct}
      />
    </div>
  );
}
