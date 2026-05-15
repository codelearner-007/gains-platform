import type { AssessmentMeta } from '@/lib/reports/types';
import { deriveAssessmentLabel } from '@/lib/reports/format';
import ReportPageHeader from './ReportPageHeader';

/**
 * Per-assessment report header used by the QRA, SDD, and IAD pages.
 *
 * These reports share the same logo + subtitle shape and differ only in
 * the title string, so the caller passes that explicitly.
 */

interface Props {
  assessment: AssessmentMeta;
  title: string;
}

export default function AssessmentReportHeader({ assessment, title }: Props) {
  // `assessment.grade` already contains "Grade <N>" (e.g. "Grade 8") for K-12
  // sections, but lower grades come through as the bare label "K". Strip a
  // leading "Grade " so we never produce "Grade Grade 8".
  const gradeLabel = assessment.grade.replace(/^Grade\s+/i, '');
  const subtitle = `Grade ${gradeLabel}: ${assessment.item_name}`;
  const meta = deriveAssessmentLabel(assessment.assessment_type);
  return (
    <ReportPageHeader
      logoUrl={assessment.school_logo_url}
      title={title}
      subtitle={subtitle}
      meta={meta}
    />
  );
}
