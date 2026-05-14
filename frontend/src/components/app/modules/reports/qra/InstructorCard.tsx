import type { AssessmentMeta, KPIs } from '@/lib/reports/types';
import { KPI_CARD_BG, LAYOUT_BORDER } from '@/lib/reports/colors';

interface InstructorCardProps {
  kpis: KPIs;
  assessment: AssessmentMeta;
}

export default function InstructorCard({ kpis, assessment }: InstructorCardProps) {
  const instructors =
    kpis.instructors && kpis.instructors.length > 0
      ? kpis.instructors
      : [assessment.section_instructors || '—'];

  return (
    <div
      className="rounded-md border flex flex-col items-center justify-center px-3 py-3 h-full"
      style={{ backgroundColor: KPI_CARD_BG, borderColor: LAYOUT_BORDER }}
    >
      <div className="text-[13px] text-black text-center leading-tight">
        Instructor(s):
      </div>
      <div className="mt-1 flex flex-col items-center justify-center gap-0.5">
        {instructors.map((name, i) => (
          <div
            key={i}
            className="text-[18px] font-bold leading-tight text-black text-center"
          >
            {name}
          </div>
        ))}
      </div>
    </div>
  );
}
