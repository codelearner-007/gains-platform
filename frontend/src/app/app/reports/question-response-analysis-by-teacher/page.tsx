'use client';

import { useSearchParams } from 'next/navigation';
import { reportsApi, reportsKeys } from '@/lib/reports/api-client';
import ReportCanvas from '@/components/app/modules/reports/shared/ReportCanvas';
import ReportBreadcrumb, {
  assessmentCrumbs,
} from '@/components/app/modules/reports/shared/ReportBreadcrumb';
import AssessmentReportHeader from '@/components/app/modules/reports/shared/AssessmentReportHeader';
import PaginatedKpiStrip from '@/components/app/modules/reports/paginated/PaginatedKpiStrip';
import PaginatedFooter from '@/components/app/modules/reports/paginated/PaginatedFooter';
import QraByTeacherTable from '@/components/app/modules/reports/paginated/QraByTeacherTable';
import ReportTypeSwitcher from '@/components/app/modules/reports/shared/ReportTypeSwitcher';
import ReportSubTabs from '@/components/app/modules/reports/shared/ReportSubTabs';
import ExportMenu from '@/components/app/modules/reports/shared/ExportMenu';
import { buildXlsxUrl } from '@/lib/reports/export-xlsx';
import AssessmentReportShell from '@/components/app/modules/reports/shared/AssessmentReportShell';
import { useAssessmentReport } from '@/components/app/modules/reports/shared/useAssessmentReport';
import { getReportBySlug } from '@/lib/reports/report-types';
import { useSelectedSchool } from '@/lib/context/SelectedSchoolContext';

const REPORT_NAME = getReportBySlug(
  'question-response-analysis-by-teacher',
).canonicalName;

export default function QraByTeacherPage() {
  const searchParams = useSearchParams();
  const itemId = searchParams.get('item_id');

  const { schoolId } = useSelectedSchool();

  const { data, isLoading, isError, error, refetch, ready } =
    useAssessmentReport({
      ready: !!itemId,
      queryKey: reportsKeys.qraByTeacher(itemId ?? '', schoolId ?? undefined),
      queryFn: () =>
        reportsApi.qraByTeacher(itemId as string, schoolId ?? undefined),
    });

  return (
    <AssessmentReportShell
      ready={ready}
      isLoading={isLoading}
      isError={isError}
      error={error}
      data={data}
      loadingLabel="Loading report…"
      onRetry={() => void refetch()}
    >
      {(data) => {
        if (!itemId) return null;
        return (
          <ReportCanvas>
            <div className="mb-3 flex flex-col gap-2 print:hidden">
              <div className="flex items-start justify-between gap-2">
                <ReportBreadcrumb
                  crumbs={assessmentCrumbs({
                    label: data.assessment.item_name || data.assessment.item_id,
                  })}
                />
                <ExportMenu
                  kind="qra-by-teacher"
                  payload={data}
                  name={data.assessment.item_name}
                  xlsxUrl={buildXlsxUrl('qra-by-teacher', {
                    itemId,
                    schoolId: schoolId ?? undefined,
                  })}
                />
              </div>
              <ReportTypeSwitcher group="assessment" itemId={itemId} />
              <ReportSubTabs family="qra" itemId={itemId} />
            </div>

            <div className="mb-2">
              <AssessmentReportHeader
                assessment={data.assessment}
                title={REPORT_NAME}
                caption="By Classroom Instructor"
                variant="dense"
              />
            </div>

            <div className="mb-2">
              <PaginatedKpiStrip kpis={data.kpis} />
            </div>

            <QraByTeacherTable teacherGroups={data.teacher_groups} />

            <PaginatedFooter />
          </ReportCanvas>
        );
      }}
    </AssessmentReportShell>
  );
}
