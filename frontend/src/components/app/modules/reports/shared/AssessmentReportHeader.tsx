import type { AssessmentMeta } from '@/lib/reports/types';
import { deriveAssessmentLabel } from '@/lib/reports/format';
import {
  buildAssessmentCourseLine,
  formatAssessmentDate,
} from '@/lib/reports/header';
import ReportPageHeader from './ReportPageHeader';

/**
 * Per-assessment report header used by the interactive QRA, SDD, and IAD pages.
 *
 * Kept field-consistent with the paginated PaginatedReportHeader (both share
 * `buildAssessmentCourseLine` + `formatAssessmentDate`): the subtitle is the
 * "<Subject> - <Grade>: <Item_Name>" course line (subject hidden when it is the
 * 'Other'/blank source catch-all), and the meta line shows the assessment type
 * and assessment date.
 */

interface Props {
  assessment: AssessmentMeta;
  title: string;
}

export default function AssessmentReportHeader({ assessment, title }: Props) {
  const subtitle = buildAssessmentCourseLine(assessment);
  const assessmentDate = formatAssessmentDate(assessment.assessment_date);
  const meta = [
    deriveAssessmentLabel(assessment.assessment_type),
    assessmentDate ? `Assessment Date: ${assessmentDate}` : '',
  ]
    .filter(Boolean)
    .join('  ·  ');
  return (
    <ReportPageHeader
      logoUrl={assessment.school_logo_url}
      schoolName={assessment.school_name || undefined}
      title={title}
      subtitle={subtitle}
      meta={meta}
    />
  );
}
