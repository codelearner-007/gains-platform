'use client';

import { useSearchParams } from 'next/navigation';
import { reportsApi, reportsKeys } from '@/lib/reports/api-client';
import ReportCanvas from '@/components/app/modules/reports/shared/ReportCanvas';
import ReportBreadcrumb, {
  assessmentCrumbs,
} from '@/components/app/modules/reports/shared/ReportBreadcrumb';
import PaginatedReportHeader from '@/components/app/modules/reports/paginated/PaginatedReportHeader';
import PaginatedFooter from '@/components/app/modules/reports/paginated/PaginatedFooter';
import QraPaginatedTable from '@/components/app/modules/reports/paginated/QraPaginatedTable';
import ReportTypeSwitcher from '@/components/app/modules/reports/shared/ReportTypeSwitcher';
import ExportMenu from '@/components/app/modules/reports/shared/ExportMenu';
import { buildXlsxUrl } from '@/lib/reports/export-xlsx';
import AssessmentReportShell from '@/components/app/modules/reports/shared/AssessmentReportShell';
import { useAssessmentReport } from '@/components/app/modules/reports/shared/useAssessmentReport';
import { getReportBySlug } from '@/lib/reports/report-types';
import { useSelectedSchool } from '@/lib/context/SelectedSchoolContext';

const REPORT_NAME = getReportBySlug(
  'question-response-analysis-paginated',
).canonicalName;

export default function QraPaginatedPage() {
  const searchParams = useSearchParams();
  const itemId = searchParams.get('item_id');

  const { schoolId } = useSelectedSchool();

  const { data, isLoading, isError, error, refetch, ready } =
    useAssessmentReport({
      ready: !!itemId,
      queryKey: reportsKeys.qraPaginated(itemId ?? '', schoolId ?? undefined),
      queryFn: () =>
        reportsApi.qraPaginated(itemId as string, schoolId ?? undefined),
    });

  return (
    <AssessmentReportShell
      ready={ready}
      isLoading={isLoading}
      isError={isError}
      error={error}
      data={data}
      loadingLabel="Loading question response analysis…"
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
                  kind="qra-paginated"
                  payload={data}
                  name={data.assessment.item_name}
                  xlsxUrl={buildXlsxUrl('qra-paginated', {
                    itemId,
                    schoolId: schoolId ?? undefined,
                  })}
                />
              </div>
              <ReportTypeSwitcher group="assessment" itemId={itemId} />
            </div>

            <div className="mb-2">
              <PaginatedReportHeader
                assessment={data.assessment}
                title={REPORT_NAME}
              />
            </div>

            {/* Legacy QRA paginated PDF has no KPI strip — intentionally omitted. */}

            <QraPaginatedTable questions={data.questions} />

            <PaginatedFooter />
          </ReportCanvas>
        );
      }}
    </AssessmentReportShell>
  );
}
