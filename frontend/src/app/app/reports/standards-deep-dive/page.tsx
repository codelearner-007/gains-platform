'use client';

import { useEffect, useMemo } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { useQuery } from '@tanstack/react-query';
import { reportsApi, reportsKeys } from '@/lib/services/reports-service';
import AssessmentReportHeader from '@/components/app/modules/reports/shared/AssessmentReportHeader';
import ReportBreadcrumb, {
  assessmentCrumbs,
} from '@/components/app/modules/reports/shared/ReportBreadcrumb';
import ReportTypeSwitcher from '@/components/app/modules/reports/shared/ReportTypeSwitcher';
import KpiStrip from '@/components/app/modules/reports/sdd/KpiStrip';
import StrandTreemap from '@/components/app/modules/reports/sdd/StrandTreemap';
import StrandRowList from '@/components/app/modules/reports/sdd/StrandRowList';
import StandardRowList from '@/components/app/modules/reports/sdd/StandardRowList';
import PerformanceBandBars from '@/components/app/modules/reports/sdd/CorrectIncorrectBars';
import SectionHeader from '@/components/app/modules/reports/shared/SectionHeader';
import ActiveFilterBar from '@/components/app/modules/reports/shared/ActiveFilterBar';
import LoadingState from '@/components/app/modules/reports/shared/LoadingState';
import ErrorState from '@/components/app/modules/reports/shared/ErrorState';
import ReportCanvas from '@/components/app/modules/reports/shared/ReportCanvas';
import AlignmentEmptyState from '@/components/app/modules/reports/shared/AlignmentEmptyState';
import { useReportFilters } from '@/lib/reports/filters';
import { deriveSdd } from '@/lib/reports/filter-helpers';

/**
 * Standards Deep Dive — layout mirrors the legacy PBIX page #16
 * (``data/_pbix_extract/50_sdd_spec.md``). Adds PowerBI-style click
 * cross-filtering: clicking a strand tile / standard row / band-chart
 * row filters every other panel on the page (except the Total Students
 * KPI, which is immune per ``08_relationships.csv:14``).
 */
export default function StandardsDeepDivePage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const itemId = searchParams.get('item_id');

  useEffect(() => {
    if (!itemId) router.replace('/app/reports');
  }, [itemId, router]);

  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: reportsKeys.sdd(itemId ?? ''),
    queryFn: () => reportsApi.sdd(itemId as string),
    enabled: !!itemId,
  });

  const { filters, setStrand, setStandard, reset, hasActiveFilter } =
    useReportFilters();

  const filtered = useMemo(
    () => (data ? deriveSdd(data, filters) : null),
    [data, filters],
  );

  if (!itemId) return null;
  if (isLoading) return <LoadingState label="Loading standards deep dive…" />;
  if (isError)
    return (
      <ErrorState
        message={
          error instanceof Error ? error.message : 'Could not load report.'
        }
        onRetry={() => void refetch()}
      />
    );
  if (!data || !filtered) return null;

  return (
    <ReportCanvas>
      <div className="mb-3 flex flex-col gap-2">
        <ReportBreadcrumb
          crumbs={assessmentCrumbs({
            label: data.assessment.item_name || data.assessment.item_id,
          })}
        />
        <ReportTypeSwitcher group="assessment" itemId={itemId} />
      </div>

      <div className="mb-2">
        <AssessmentReportHeader
          assessment={data.assessment}
          title="Standards Deep Dive"
        />
      </div>

      <div className="mb-2" style={{ minHeight: 100 }}>
        <KpiStrip kpis={filtered.kpis} />
      </div>

      {hasActiveFilter && (
        <ActiveFilterBar filters={filters} onClear={reset} />
      )}

      {data.data_quality?.alignment_status === 'missing' && (
        <AlignmentEmptyState
          quality={data.data_quality}
          reportLabel="Standards Deep Dive"
          displayMode="banner"
        />
      )}

      <div className="mb-2">
        <SectionHeader title="Number of Standards by Strand" />
        <div className="grid grid-cols-1 md:grid-cols-2 gap-2 mt-2">
          <div className="min-w-0">
            <StrandRowList
              strands={filtered.strands_rollup}
              selectedStrand={filters.strand}
              onSelectStrand={setStrand}
            />
          </div>
          <div className="min-w-0">
            <StrandTreemap
              strands={filtered.strands_rollup}
              selectedStrand={filters.strand}
              onSelectStrand={setStrand}
            />
          </div>
        </div>
      </div>

      <div>
        <SectionHeader title="Standards by their performance" />
        <div className="grid grid-cols-1 md:grid-cols-12 gap-2 mt-2">
          <div className="md:col-span-3 min-w-0">
            <StandardRowList
              standards={filtered.standards_rollup}
              selectedStandard={filters.standard}
              onSelectStandard={setStandard}
            />
          </div>
          <div className="md:col-span-9 min-w-0">
            <PerformanceBandBars
              bandHigh={filtered.band_high}
              bandMid={filtered.band_mid}
              bandLow={filtered.band_low}
              selectedStandard={filters.standard}
              onSelectStandard={setStandard}
            />
          </div>
        </div>
      </div>
    </ReportCanvas>
  );
}
