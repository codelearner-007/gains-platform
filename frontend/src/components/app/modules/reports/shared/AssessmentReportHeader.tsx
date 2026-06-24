import type { AssessmentMeta } from '@/lib/reports/types';
import { deriveAssessmentLabel } from '@/lib/reports/format';
import {
  buildAssessmentCourseLine,
  formatAssessmentDate,
} from '@/lib/reports/header';
import ReportPageHeader from './ReportPageHeader';

/**
 * THE per-assessment report header — used by every assessment report view:
 * the interactive QRA/SDD/IAD pages (default variant) and the paginated
 * QSR / QRA-paginated / by-teacher / by-standard-teacher views (`dense`).
 *
 * The subtitle is the "<Subject> - <Grade>: <Item_Name>" course line (subject
 * hidden when it is the 'Other'/blank source catch-all); the meta line shows
 * the assessment type and date (plus the section instructor on dense/paginated
 * views, mirroring the legacy SSRS header). All field formatting flows through
 * the shared `buildAssessmentCourseLine` + `formatAssessmentDate` helpers, and
 * the logo/school-name comes straight from the payload's AssessmentMeta.
 */

interface Props {
  assessment: AssessmentMeta;
  title: string;
  /** Optional italic caption (e.g. QRA "By Classroom Instructor"). */
  caption?: string;
  /** `dense` = compact paginated/print header (smaller logo + title). */
  variant?: 'default' | 'dense';
}

export default function AssessmentReportHeader({
  assessment,
  title,
  caption,
  variant = 'default',
}: Props) {
  const subtitle = buildAssessmentCourseLine(assessment);
  const assessmentDate = formatAssessmentDate(assessment.assessment_date);
  const meta = [
    deriveAssessmentLabel(assessment.assessment_type),
    variant === 'dense' ? assessment.section_instructors : '',
    assessmentDate ? `Assessment Date: ${assessmentDate}` : '',
  ]
    .filter(Boolean)
    .join('  ·  ');
  return (
    <ReportPageHeader
      logoUrl={assessment.school_logo_url}
      schoolName={assessment.school_name || undefined}
      title={title}
      caption={caption}
      subtitle={subtitle}
      meta={meta}
      variant={variant}
    />
  );
}
