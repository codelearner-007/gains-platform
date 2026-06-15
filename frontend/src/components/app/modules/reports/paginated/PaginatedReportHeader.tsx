import type { AssessmentMeta } from '@/lib/reports/types';
import { LAYOUT_BORDER } from '@/lib/reports/colors';

interface Props {
  assessment: AssessmentMeta;
  title: string;
  /** Optional descriptive caption (e.g. QRA "By Classroom Instructor"). */
  subtitle?: string;
  /**
   * Render the legacy QRA paginated "<Instructor>  Assessment Date: M/D/YYYY"
   * line. Off by default so the QSR paginated header (no instructor line)
   * stays untouched.
   */
  showInstructorLine?: boolean;
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
 *   • Instructor + "Assessment Date: M/D/YYYY" line (legacy QRA paginated).
 * Legacy paginated PDFs carry NO school logo, so none is rendered here.
 */

/** Format an ISO date (YYYY-MM-DD) as legacy M/D/YYYY, with no timezone shift. */
function formatAssessmentDate(iso: string | null): string {
  if (!iso) return '';
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso);
  if (!m) return '';
  const [, y, mo, d] = m;
  return `${Number(mo)}/${Number(d)}/${y}`;
}

export default function PaginatedReportHeader({
  assessment,
  title,
  subtitle,
  showInstructorLine = false,
}: Props) {
  const courseLine = [
    [assessment.subject, assessment.grade].filter(Boolean).join(' - '),
    assessment.item_name,
  ]
    .filter(Boolean)
    .join(': ');

  const assessmentDate = formatAssessmentDate(assessment.assessment_date);
  const instructorLine = [
    assessment.section_instructors,
    assessmentDate ? `Assessment Date: ${assessmentDate}` : '',
  ]
    .filter(Boolean)
    .join('    ');
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
      {showInstructorLine && instructorLine && (
        <div className="text-[12px] text-neutral-700 leading-tight whitespace-pre truncate">
          {instructorLine}
        </div>
      )}
    </div>
  );
}
