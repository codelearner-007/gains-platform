'use client';

import { useQuery } from '@tanstack/react-query';
import { reportsApi, reportsKeys } from '@/lib/reports/api-client';
import ReportPageHeader from '@/components/app/modules/reports/shared/ReportPageHeader';
import KpiStrip from '@/components/app/modules/reports/ytd/KpiStrip';
import OverallTrendChart from '@/components/app/modules/reports/ytd/OverallTrendChart';
import GradeDistributionChart from '@/components/app/modules/reports/ytd/GradeDistributionChart';
import StudentProgressionChart from '@/components/app/modules/reports/ytd/StudentProgressionChart';
import StrandHeatmap from '@/components/app/modules/reports/ytd/StrandHeatmap';
import MostImprovedDroppedTable from '@/components/app/modules/reports/ytd/MostImprovedDroppedTable';
import LoadingState from '@/components/app/modules/reports/shared/LoadingState';
import ErrorState from '@/components/app/modules/reports/shared/ErrorState';
import ReportCanvas from '@/components/app/modules/reports/shared/ReportCanvas';
import ReportBreadcrumb, {
  programCrumbs,
} from '@/components/app/modules/reports/shared/ReportBreadcrumb';
import ReportTypeSwitcher from '@/components/app/modules/reports/shared/ReportTypeSwitcher';

export default function YearToDatePerformancePage() {
  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: reportsKeys.ytd(),
    queryFn: () => reportsApi.ytd(),
  });

  if (isLoading) return <LoadingState label="Loading year-to-date performance…" />;
  if (isError)
    return (
      <ErrorState
        message={
          error instanceof Error
            ? error.message
            : 'Could not load report.'
        }
        onRetry={() => void refetch()}
      />
    );
  if (!data) return null;

  const subtitleParts = [
    data.school.current_session
      ? `Academic year ${data.school.current_session}`
      : null,
    data.period.date_from && data.period.date_to
      ? `${data.period.date_from} – ${data.period.date_to}`
      : null,
    data.kpis.total_assessments
      ? `${data.kpis.total_assessments} assessment${data.kpis.total_assessments === 1 ? '' : 's'}`
      : null,
  ].filter(Boolean) as string[];
  const subtitle =
    subtitleParts.length > 0
      ? subtitleParts.join(' • ')
      : 'Cross-assessment performance dashboard';

  return (
    <ReportCanvas>
      <div className="mb-3 flex flex-col gap-2">
        <ReportBreadcrumb crumbs={programCrumbs('Year-To-Date Performance')} />
        <ReportTypeSwitcher group="program" />
      </div>

      <div className="mb-2">
        <ReportPageHeader
          logoUrl={data.school.logo_url}
          title="Year-To-Date Performance"
          subtitle={subtitle}
          meta={data.school.name || undefined}
        />
      </div>

      <div className="mb-2" style={{ minHeight: 100 }}>
        <KpiStrip kpis={data.kpis} />
      </div>

      <div className="grid grid-cols-12 gap-2 mb-2">
        <div className="col-span-12 lg:col-span-7">
          <OverallTrendChart timeline={data.timeline} />
        </div>
        <div className="col-span-12 lg:col-span-5">
          <GradeDistributionChart data={data.grade_distribution} />
        </div>
      </div>

      <div className="mb-2">
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
    </ReportCanvas>
  );
}
