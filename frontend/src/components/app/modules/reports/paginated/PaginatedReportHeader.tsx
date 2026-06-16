import type { AssessmentMeta } from '@/lib/reports/types';
import { LAYOUT_BORDER } from '@/lib/reports/colors';
import { deriveAssessmentLabel } from '@/lib/reports/format';
import {
  buildAssessmentCourseLine,
  formatAssessmentDate,
} from '@/lib/reports/header';

interface Props {
  assessment: AssessmentMeta;
  title: string;
  /** Optional descriptive caption (e.g. QRA "By Classroom Instructor"). */
  subtitle?: string;
}

/**
 * Header strip for the paginated report family.
 *
 * Matches the legacy SSRS header (PAG-9), as rendered in the sample PDFs, and is
 * kept field-consistent with the interactive AssessmentReportHeader (both share
 * `buildAssessmentCourseLine` + `formatAssessmentDate`):
 *   • Big bold H1 title ("Question Summary Report")
 *   • Optional variant caption ("By Classroom Instructor")
 *   • Assessment-type line ("Unit Test" / "Lesson Assessments")
 *   • Course line "<Subject> - <Grade>: <Item_Name>" — subject hidden when it is
 *     the 'Other'/blank source catch-all; redundant grade "N - " prefix stripped.
 *   • Instructor + "Assessment Date: M/D/YYYY" line (shown on every variant for
 *     consistency).
 * Legacy paginated PDFs carry NO school logo, so none is rendered here.
 */
export default function PaginatedReportHeader({
  assessment,
  title,
  subtitle,
}: Props) {
  const courseLine = buildAssessmentCourseLine(assessment);
  const assessmentType = deriveAssessmentLabel(assessment.assessment_type);
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
      {assessmentType && (
        <div className="text-[12px] text-neutral-700 leading-tight mt-0.5 truncate">
          {assessmentType}
        </div>
      )}
      <div className="text-[13px] text-black leading-tight truncate">
        {courseLine}
      </div>
      {instructorLine && (
        <div className="text-[12px] text-neutral-700 leading-tight whitespace-pre truncate">
          {instructorLine}
        </div>
      )}
    </div>
  );
}
