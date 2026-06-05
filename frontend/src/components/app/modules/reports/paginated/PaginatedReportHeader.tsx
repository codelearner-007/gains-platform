import type { AssessmentMeta } from '@/lib/reports/types';
import { LAYOUT_BORDER } from '@/lib/reports/colors';

interface Props {
  assessment: AssessmentMeta;
  title: string;
  /** Optional descriptive caption (e.g. QRA "By Classroom Instructor"). */
  subtitle?: string;
}

/**
 * Header strip for the paginated report family.
 *
 * Matches the legacy SSRS header (PAG-9), as rendered in the sample PDFs:
 *   • Big bold H1 title ("Question Summary Report")
 *   • Assessment-type line ("Unit Test" / "Lesson Assessments")
 *   • Course line "<Subject> - <Grade>: <Item_Name>" — NO "Course:" prefix
 *     (e.g. "Science - Grade 3: Unit 6 Test: Heat Sources"); `grade` already
 *     carries the "Grade N" prefix from the cube.
 * Legacy paginated PDFs carry NO school logo, so none is rendered here.
 */
export default function PaginatedReportHeader({
  assessment,
  title,
  subtitle,
}: Props) {
  const courseLine = [
    [assessment.subject, assessment.grade].filter(Boolean).join(' - '),
    assessment.item_name,
  ]
    .filter(Boolean)
    .join(': ');
  return (
    <div
      className="bg-white border px-3 py-2"
      style={{ borderColor: LAYOUT_BORDER }}
    >
      <div className="text-[18px] font-bold text-black leading-tight">
        {title}
      </div>
      {subtitle && (
        <div className="text-[12px] italic text-neutral-700 leading-tight">
          {subtitle}
        </div>
      )}
      {assessment.assessment_type && (
        <div className="text-[12px] text-neutral-700 leading-tight mt-0.5 truncate">
          {assessment.assessment_type}
        </div>
      )}
      <div className="text-[13px] text-black leading-tight truncate">
        {courseLine}
      </div>
    </div>
  );
}
