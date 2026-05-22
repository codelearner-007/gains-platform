'use client';

import { useQuery } from '@tanstack/react-query';

import { reportsApi, reportsKeys } from '@/lib/reports/api-client';
import type { AssessmentFilters } from '@/lib/reports/types';
import { useSummaryFilters } from '@/lib/reports/use-summary-filters';

import ReportPageHeader from '@/components/app/modules/reports/shared/ReportPageHeader';
import ReportCanvas from '@/components/app/modules/reports/shared/ReportCanvas';
import ReportBreadcrumb, {
  programCrumbs,
} from '@/components/app/modules/reports/shared/ReportBreadcrumb';
import ReportTypeSwitcher from '@/components/app/modules/reports/shared/ReportTypeSwitcher';
import ReportFilters from '@/components/app/modules/reports/shared/ReportFilters';
import ReportAdditionalInsights from '@/components/app/modules/reports/shared/ReportAdditionalInsights';
import LoadingState from '@/components/app/modules/reports/shared/LoadingState';
import ErrorState from '@/components/app/modules/reports/shared/ErrorState';

import KpiStrip from '@/components/app/modules/reports/ytd/KpiStrip';
import YtdReportChrome from '@/components/app/modules/reports/ytd/YtdReportChrome';
import OverallTrendChart from '@/components/app/modules/reports/ytd/OverallTrendChart';
import GradeDistributionChart from '@/components/app/modules/reports/ytd/GradeDistributionChart';
import StudentProgressionChart from '@/components/app/modules/reports/ytd/StudentProgressionChart';
import StrandHeatmap from '@/components/app/modules/reports/ytd/StrandHeatmap';
import MostImprovedDroppedTable from '@/components/app/modules/reports/ytd/MostImprovedDroppedTable';

const BASE_PATH = '/app/reports/year-to-date-performance';

export default function YearToDatePerformancePage() {
  const { filters, setFilters } = useSummaryFilters<AssessmentFilters>({
    basePath: BASE_PATH,
  });

  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: reportsKeys.ytd(filters),
    queryFn: () => reportsApi.ytd(filters),
  });

  if (isLoading) return <LoadingState label="Loading year-to-date performance…" />;
  if (isError)
    return (
      <ErrorState
        message={
          error instanceof Error ? error.message : 'Could not load report.'
        }
        onRetry={() => void refetch()}
      />
    );
  if (!data) return null;

  return (
    <ReportCanvas>
      <div className="mb-3 flex flex-col gap-2">
        <ReportBreadcrumb crumbs={programCrumbs('Year To Date - Longitudinal Report')} />
        <ReportTypeSwitcher group="program" />
      </div>

      <div className="mb-2">
        <ReportPageHeader
          logoUrl={data.school.logo_url}
          title="Year To Date - Longitudinal Report"
          subtitle={
            data.school.current_session
              ? `Academic year ${data.school.current_session}`
              : 'Cross-assessment performance dashboard'
          }
          meta={data.school.name || undefined}
        />
      </div>

      <div className="mb-3">
        <ReportFilters value={filters} onChange={setFilters} />
      </div>

      <div className="mb-3">
        <YtdReportChrome school={data.school} period={data.period} />
      </div>

      <div className="mb-2" style={{ minHeight: 100 }}>
        <KpiStrip kpis={data.kpis} />
      </div>

      <ReportAdditionalInsights>
        <div className="grid grid-cols-12 gap-2">
          <div className="col-span-12 lg:col-span-7">
            <OverallTrendChart timeline={data.timeline} />
          </div>
          <div className="col-span-12 lg:col-span-5">
            <GradeDistributionChart data={data.grade_distribution} />
          </div>
        </div>

        <div>
          <StrandHeatmap cells={data.strand_heatmap} />
        </div>

        <div className="grid grid-cols-12 gap-2">
          <div className="col-span-12 lg:col-span-8">
            <StudentProgressionChart data={data.student_progression} />
          </div>
          <div className="col-span-12 lg:col-span-4">
            <MostImprovedDroppedTable
              mostImproved={data.kpis.most_improved}
              biggestDrops={data.kpis.biggest_drops}
            />
          </div>
        </div>
      </ReportAdditionalInsights>
    </ReportCanvas>
  );
}
