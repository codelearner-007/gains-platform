'use client';

import { useSearchParams } from 'next/navigation';
import { reportsApi, reportsKeys } from '@/lib/reports/api-client';
import AssessmentReportHeader from '@/components/app/modules/reports/shared/AssessmentReportHeader';
import ReportBreadcrumb, {
  assessmentCrumbs,
} from '@/components/app/modules/reports/shared/ReportBreadcrumb';
import ReportTypeSwitcher from '@/components/app/modules/reports/shared/ReportTypeSwitcher';
import ExportMenu from '@/components/app/modules/reports/shared/ExportMenu';
import { buildXlsxUrl } from '@/lib/reports/export-xlsx';
import { getReportBySlug } from '@/lib/reports/report-types';
import ReportCanvas from '@/components/app/modules/reports/shared/ReportCanvas';
import QuestionContextCard from '@/components/app/modules/reports/iad/QuestionContextCard';
import KpiStrip from '@/components/app/modules/reports/iad/KpiStrip';
import DistractorTable from '@/components/app/modules/reports/iad/DistractorTable';
import DistractorTreemap from '@/components/app/modules/reports/iad/DistractorTreemap';
import DistractorChart from '@/components/app/modules/reports/iad/DistractorChart';
import StudentAttemptTable from '@/components/app/modules/reports/iad/StudentAttemptTable';
import ReportAdditionalInsights from '@/components/app/modules/reports/shared/ReportAdditionalInsights';
import AssessmentReportShell from '@/components/app/modules/reports/shared/AssessmentReportShell';
import { useAssessmentReport } from '@/components/app/modules/reports/shared/useAssessmentReport';
import { useSelectedSchool } from '@/lib/context/SelectedSchoolContext';

const REPORT_NAME = getReportBySlug('incorrect-answer-details').canonicalName;

export default function IncorrectAnswerDetailsPage() {
  const searchParams = useSearchParams();
  const itemId = searchParams.get('item_id');
  const questionId = searchParams.get('question_id');

  const { schoolId } = useSelectedSchool();

  const { data, isLoading, isError, error, refetch, ready } =
    useAssessmentReport({
      ready: !!itemId && !!questionId,
      queryKey: reportsKeys.iad(
        itemId ?? '',
        questionId ?? '',
        schoolId ?? undefined,
      ),
      queryFn: () =>
        reportsApi.iad(
          itemId as string,
          questionId as string,
          schoolId ?? undefined,
        ),
    });

  return (
    <AssessmentReportShell
      ready={ready}
      isLoading={isLoading}
      isError={isError}
      error={error}
      data={data}
      loadingLabel="Loading question deep dive…"
      onRetry={() => void refetch()}
    >
      {(data) => {
        if (!itemId || !questionId) return null;
        return (
          <ReportCanvas>
            <div className="mb-3 flex flex-col gap-2 print:hidden">
              <div className="flex items-start justify-between gap-2">
                <ReportBreadcrumb
                  crumbs={assessmentCrumbs(
                    {
                      label:
                        data.assessment.item_name || data.assessment.item_id,
                      href: `/app/reports/question-response-analysis?item_id=${itemId}`,
                    },
                    {
                      label: `Question ${data.question.question_no || data.question.position_number}`,
                    },
                  )}
                />
                <ExportMenu
                  kind="iad"
                  payload={data}
                  name={`${data.assessment.item_name}-q${data.question.question_no || data.question.position_number}`}
                  xlsxUrl={buildXlsxUrl('iad', {
                    itemId,
                    questionId,
                    schoolId: schoolId ?? undefined,
                  })}
                />
              </div>
              <ReportTypeSwitcher
                group="assessment"
                itemId={itemId}
                questionId={questionId}
              />
            </div>

            <div className="mb-2">
              <AssessmentReportHeader
                assessment={data.assessment}
                title={REPORT_NAME}
              />
            </div>

            <div className="mb-2">
              <QuestionContextCard question={data.question} />
            </div>

            <div className="mb-2" style={{ minHeight: 100 }}>
              <KpiStrip kpis={data.kpis} />
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-2 mb-2">
              <DistractorTable rows={data.distractors} />
              <DistractorTreemap rows={data.distractors} />
            </div>

            <div>
              {/* Cube-only (parquet-loaded) schools return no per-student attempts
                  but still carry valid cube-derived KPIs / distractors above. */}
              <StudentAttemptTable
                attempts={data.student_attempts}
                perStudentAvailable={data.student_attempts.length > 0}
              />
            </div>

            <ReportAdditionalInsights>
              <DistractorChart rows={data.distractors} />
            </ReportAdditionalInsights>
          </ReportCanvas>
        );
      }}
    </AssessmentReportShell>
  );
}
