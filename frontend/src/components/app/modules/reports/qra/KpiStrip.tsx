import type { KPIs } from '@/lib/reports/types';
import KpiCard from '@/components/app/modules/reports/shared/KpiCard';

const CARD_CLASSNAME = 'min-h-[100px]';
const VALUE_CLASSNAME = 'text-[22px]';

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
 * QRA KPI strip — seven tiles: Instructor + six measures.
 * Responsive grid: 1 col phone, 2 cols sm, 4 cols md, 7 cols xl.
 * The Instructor card lives inside the strip so the Summary-by-Standards
 * section below renders full-width.
 */
export default function KpiStrip({ kpis }: { kpis: KPIs }) {
  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 xl:grid-cols-7 gap-2 w-full h-full">
      <KpiCard
        className={CARD_CLASSNAME}
        valueClassName="text-[14px]"
        label="Instructor(s)"
        value={<InstructorsValue instructors={kpis.instructors} />}
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
        label="Number of Questions"
        value={String(kpis.total_questions)}
      />
      <KpiCard
        className={CARD_CLASSNAME}
        valueClassName={VALUE_CLASSNAME}
        label="Number of Standards"
        value={String(kpis.total_standards)}
      />
      <KpiCard
        className={CARD_CLASSNAME}
        valueClassName={VALUE_CLASSNAME}
        label="Grade Average"
        value={kpis.grade_average_pct}
      />
      <KpiCard
        className={CARD_CLASSNAME}
        valueClassName={VALUE_CLASSNAME}
        label="Overall Highest %"
        value={kpis.grade_max_pct}
      />
      <KpiCard
        className={CARD_CLASSNAME}
        valueClassName={VALUE_CLASSNAME}
        label="Overall Lowest %"
        value={kpis.grade_min_pct}
      />
    </div>
  );
}
