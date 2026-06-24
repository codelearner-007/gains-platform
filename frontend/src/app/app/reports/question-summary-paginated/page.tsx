'use client';

import { useSearchParams } from 'next/navigation';
import { reportsApi, reportsKeys } from '@/lib/reports/api-client';
import ReportCanvas from '@/components/app/modules/reports/shared/ReportCanvas';
import ReportBreadcrumb, {
  assessmentCrumbs,
} from '@/components/app/modules/reports/shared/ReportBreadcrumb';
import AssessmentReportHeader from '@/components/app/modules/reports/shared/AssessmentReportHeader';
import PaginatedFooter from '@/components/app/modules/reports/paginated/PaginatedFooter';
import QuestionSummaryMatrix from '@/components/app/modules/reports/paginated/QuestionSummaryMatrix';
import ReportTypeSwitcher from '@/components/app/modules/reports/shared/ReportTypeSwitcher';
import ReportVariantTabs from '@/components/app/modules/reports/shared/ReportVariantTabs';
import ExportMenu from '@/components/app/modules/reports/shared/ExportMenu';
import { buildXlsxUrl } from '@/lib/reports/export-xlsx';
import AssessmentReportShell from '@/components/app/modules/reports/shared/AssessmentReportShell';
import { useAssessmentReport } from '@/components/app/modules/reports/shared/useAssessmentReport';
import { getReportBySlug } from '@/lib/reports/report-types';
import { useSelectedSchool } from '@/lib/context/SelectedSchoolContext';

const QSR_NAME = getReportBySlug('question-summary-paginated').canonicalName;

// Legacy QSR paginated variants (each is its own SSRS .rdl / PBIX page):
//   • base             — PBIX ord 6 "Question Summary Report"
//   • teacher          — PBIX ord 7 "- Teacher Subtotal" per-instructor subtotal block
//   • redacted         — PBIX ord 17 "- names redacted" (client-side; see matrix note)
//   • header-highlights — PBIX ord 16 "- header highlights" (== legacy "...- color.rdl"):
//                         base layout + the two header bands performance-colored.
type Variant = 'base' | 'teacher' | 'redacted' | 'header-highlights';

function parseVariant(raw: string | null): Variant {
  if (raw === 'teacher' || raw === 'redacted' || raw === 'header-highlights') {
    return raw;
  }
  return 'base';
}

export default function QuestionSummaryPaginatedPage() {
  const searchParams = useSearchParams();
  const itemId = searchParams.get('item_id');
  const variant = parseVariant(searchParams.get('variant'));

  const { schoolId } = useSelectedSchool();

  const { data, isLoading, isError, error, refetch, ready } =
    useAssessmentReport({
      ready: !!itemId,
      queryKey: reportsKeys.questionSummaryPaginated(
        itemId ?? '',
        schoolId ?? undefined,
      ),
      queryFn: () =>
        reportsApi.questionSummaryPaginated(
          itemId as string,
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
      loadingLabel="Loading question summary…"
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
                  kind="qsr"
                  payload={data}
                  name={data.assessment.item_name}
                  xlsxUrl={buildXlsxUrl('qsr', {
                    itemId,
                    schoolId: schoolId ?? undefined,
                  })}
                />
              </div>
              <ReportTypeSwitcher group="assessment" itemId={itemId} />
              <ReportVariantTabs
                pathname="/app/reports/question-summary-paginated"
                baseQuery={{ item_id: itemId }}
                options={[
                  { value: 'base', label: 'Base' },
                  { value: 'teacher', label: 'Teacher Subtotal' },
                  { value: 'header-highlights', label: 'Header Highlights' },
                  { value: 'redacted', label: 'Names Redacted' },
                ]}
                active={variant}
                defaultValue="base"
                ariaLabel="Question Summary Report variant"
              />
            </div>

            <div className="mb-2">
              <AssessmentReportHeader
                assessment={data.assessment}
                title={QSR_NAME}
                variant="dense"
              />
            </div>

            {/* PAG-3: legacy QSR has no KPI strip — intentionally omitted. */}

            <QuestionSummaryMatrix
              payload={data}
              showTeacherSubtotal={variant === 'teacher'}
              redacted={variant === 'redacted'}
              headerHighlights={variant === 'header-highlights'}
            />

            <PaginatedFooter />
          </ReportCanvas>
        );
      }}
    </AssessmentReportShell>
  );
}
