'use client';

import { useMemo, useState, type Dispatch, type SetStateAction } from 'react';
import { useSearchParams } from 'next/navigation';
import { useQuery } from '@tanstack/react-query';
import { CheckCircle2, Telescope } from 'lucide-react';
import { reportsApi, reportsKeys } from '@/lib/reports/api-client';
import type { ForwardViewFilters, ForwardViewPayload } from '@/lib/reports/types';
import { useSummaryFilters } from '@/lib/reports/use-summary-filters';
import { useEffectiveSession } from '@/lib/reports/use-latest-session';
import { useSelectedSchool } from '@/lib/context/SelectedSchoolContext';
import ReportPageHeader from '@/components/app/modules/reports/shared/ReportPageHeader';
import ReportCanvas from '@/components/app/modules/reports/shared/ReportCanvas';
import ReportScopePrompt from '@/components/app/modules/reports/shared/ReportScopePrompt';
import LoadingState from '@/components/app/modules/reports/shared/LoadingState';
import ErrorState from '@/components/app/modules/reports/shared/ErrorState';
import ReportFilters from '@/components/app/modules/reports/shared/ReportFilters';
import ReportBreadcrumb, {
  programCrumbs,
} from '@/components/app/modules/reports/shared/ReportBreadcrumb';
import ReportTypeSwitcher from '@/components/app/modules/reports/shared/ReportTypeSwitcher';
import ExportMenu from '@/components/app/modules/reports/shared/ExportMenu';
import SectionHeader from '@/components/app/modules/reports/shared/SectionHeader';
import KpiStrip, {
  type KpiTile,
} from '@/components/app/modules/reports/shared/KpiStrip';
import AlignmentEmptyState from '@/components/app/modules/reports/shared/AlignmentEmptyState';
import { Button } from '@/components/ui/button';
import { buildXlsxUrl } from '@/lib/reports/export-xlsx';
import { getReportBySlug } from '@/lib/reports/report-types';
import ThresholdControl from '@/components/app/modules/reports/forward-view/ThresholdControl';
import PeriodSection from '@/components/app/modules/reports/forward-view/PeriodSection';
import TopFocusStrip from '@/components/app/modules/reports/forward-view/TopFocusStrip';

const BASE_PATH = '/app/reports/forward-view';
const REPORT_NAME = getReportBySlug('forward-view').canonicalName;
const DEFAULT_THRESHOLD_PCT = 70;

/** Parse the URL `?threshold` percent int; default 70 when absent/invalid. */
function parseThresholdPct(raw: string | null): number {
  if (!raw) return DEFAULT_THRESHOLD_PCT;
  const n = Number.parseInt(raw, 10);
  return Number.isFinite(n) ? n : DEFAULT_THRESHOLD_PCT;
}

export default function ForwardViewPage() {
  const searchParams = useSearchParams();
  const thresholdParam = searchParams.get('threshold');
  const thresholdPct = parseThresholdPct(thresholdParam);
  // Percent int → fraction string at the api boundary (backend expects 0.05–0.95).
  const apiThreshold = String(thresholdPct / 100);

  const { filters, setFilters } = useSummaryFilters<ForwardViewFilters>({
    basePath: BASE_PATH,
    preserveParams: { threshold: thresholdParam ?? undefined },
  });
  const { schoolId } = useSelectedSchool();

  // Session defaults to the school's latest, resolved on the frontend and always
  // sent explicitly, so the report never fetches without a concrete session.
  const { session: effectiveSession } = useEffectiveSession(
    schoolId,
    filters.session,
  );

  // Body defaults to flagged-only; the toggle reveals the full ranked list. Kept
  // in the page (not the body) so it survives a refetch's loading flash.
  const [flaggedOnly, setFlaggedOnly] = useState(true);

  // Gate: Forward View is built for one subject + grade + session at a time.
  const scoped = Boolean(filters.subject && filters.grade && effectiveSession);

  const queryFilters = useMemo<ForwardViewFilters>(
    () => ({
      ...filters,
      session: effectiveSession,
      school_id: schoolId ?? undefined,
      threshold: apiThreshold,
    }),
    [filters, effectiveSession, schoolId, apiThreshold],
  );

  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: reportsKeys.forwardView(queryFilters),
    queryFn: () => reportsApi.forwardView(queryFilters),
    enabled: Boolean(schoolId) && scoped,
  });

  // XLSX carries the same filter scope + resolved session + threshold fraction;
  // the backend resolves the session exactly as the JSON endpoint does.
  const xlsxFilters: ForwardViewFilters = {
    ...filters,
    session: effectiveSession,
    threshold: apiThreshold,
  };
  const xlsxUrl = buildXlsxUrl('forward-view', {
    schoolId: schoolId ?? undefined,
    filters: xlsxFilters,
  });

  const schoolName = data?.school.name || undefined;

  return (
    <ReportCanvas>
      <div className="mb-3 flex flex-col gap-2 print:hidden">
        <div className="flex items-start justify-between gap-2">
          <ReportBreadcrumb crumbs={programCrumbs(REPORT_NAME)} />
          <ExportMenu
            kind="forward-view"
            payload={data}
            name={schoolName || 'forward-view'}
            xlsxUrl={xlsxUrl}
          />
        </div>
        <ReportTypeSwitcher group="program" />
        <ReportFilters
          value={filters}
          onChange={setFilters}
          showSection
          requireScope
          resolvedSession={effectiveSession}
          extras={<ThresholdControl value={thresholdPct} />}
        />
      </div>

      {!scoped ? (
        <ReportScopePrompt session={effectiveSession} />
      ) : isLoading ? (
        <LoadingState label="Loading forward view…" />
      ) : isError ? (
        <ErrorState
          message={
            error instanceof Error ? error.message : 'Could not load report.'
          }
          onRetry={() => void refetch()}
        />
      ) : !data ? null : (
        <ForwardViewBody
          data={data}
          flaggedOnly={flaggedOnly}
          setFlaggedOnly={setFlaggedOnly}
          onViewCurrent={() =>
            setFilters({ ...filters, session: data.school.current_session })
          }
        />
      )}
    </ReportCanvas>
  );
}

interface ForwardViewBodyProps {
  data: ForwardViewPayload;
  flaggedOnly: boolean;
  setFlaggedOnly: Dispatch<SetStateAction<boolean>>;
  /** Pivot the Session slicer to the school's current session. */
  onViewCurrent: () => void;
}

/**
 * The scoped Forward View body: identity header, KPI strip, top-focus standards
 * and the per-period / per-unit breakdown. Rendered only once a subject + grade
 * + session are resolved and the payload has loaded. Copy is session-aware: the
 * `resolvedSession` echoed by the backend drives past-vs-current phrasing.
 */
function ForwardViewBody({
  data,
  flaggedOnly,
  setFlaggedOnly,
  onViewCurrent,
}: ForwardViewBodyProps) {
  const k = data.kpis;
  const resolvedSession = data.filters_applied.session;
  const schoolName = data.school.name || undefined;
  const isCurrentSession = data.school.current_session === resolvedSession;

  const subtitle = `Based on ${resolvedSession} results • ${k.flagged_standards} of ${k.standards_assessed} standards flagged below ${k.threshold_pct}`;

  const meta = isCurrentSession
    ? 'Where students have struggled so far this year — focus here as you plan upcoming instruction.'
    : `Where students struggled in ${resolvedSession} — focus here first as you plan this year's instruction.`;

  const tiles: KpiTile[] = [
    {
      label: 'Standards Assessed',
      value: k.standards_assessed,
      valueClassName: 'text-[24px]',
      hint: 'Distinct standard codes assessed in the current scope',
    },
    {
      label: 'Flagged Standards',
      value: k.flagged_standards,
      valueClassName: 'text-[24px]',
      hint: `Distinct standards whose pooled % correct across the whole scope is below ${k.threshold_pct}`,
    },
    {
      label: 'Flag Rate',
      value: k.flag_rate_pct,
      valueClassName: 'text-[24px]',
      hint: 'Flagged ÷ assessed standards',
    },
    {
      label: 'Units Covered',
      value: k.units_covered,
      valueClassName: 'text-[24px]',
      hint: 'Distinct assessments (units) in scope',
    },
    {
      label: 'Periods Covered',
      value: k.periods_covered,
      valueClassName: 'text-[24px]',
      hint: 'Distinct assessment categories (e.g. Lesson Assessments)',
    },
  ];

  const hasData = data.periods.length > 0;
  const canPivot = data.school.current_session !== resolvedSession;
  const noneFlagged = k.flagged_standards === 0;

  return (
    <>
      <div className="mb-2">
        <ReportPageHeader
          logoUrl={data.school.logo_url}
          schoolName={schoolName}
          title={REPORT_NAME}
          subtitle={subtitle}
          meta={meta}
        />
      </div>

      {data.data_quality?.alignment_status === 'missing' && (
        <AlignmentEmptyState
          quality={data.data_quality}
          reportLabel={REPORT_NAME}
          displayMode="banner"
        />
      )}

      {!hasData ? (
        <div className="flex w-full justify-center py-6">
          <div
            className="flex flex-col items-center gap-4 rounded-lg border border-border bg-card p-8 text-center"
            style={{ maxWidth: 520 }}
          >
            <Telescope className="h-10 w-10 text-muted-foreground" />
            <div className="space-y-1">
              <h2 className="text-lg font-semibold text-foreground">
                No {resolvedSession} assessment data for{' '}
                {schoolName ?? 'this school'} yet
              </h2>
              <p className="text-sm text-muted-foreground">
                Forward View flags the standards students struggled with in the
                selected session. Nothing is recorded for {resolvedSession} under
                the current filters.
              </p>
            </div>
            {canPivot && (
              <Button variant="outline" onClick={onViewCurrent}>
                View {data.school.current_session} instead
              </Button>
            )}
          </div>
        </div>
      ) : (
        <>
          <div className="mb-2">
            <KpiStrip cols={5} tiles={tiles} />
            <p className="mt-1 text-xs text-muted-foreground">
              Counts are distinct standards in the current scope — a standard can
              be flagged in one assessment yet clear overall. Flagged = pooled %
              correct below {k.threshold_pct}. % correct = points earned ÷ points
              possible, pooled across all students.
            </p>
          </div>

          <div className="mb-3">
            <SectionHeader
              title={`Top focus standards — lowest % correct in ${resolvedSession}`}
            />
            <div className="mt-2">
              {noneFlagged ? (
                <div className="flex items-center gap-2 rounded-lg border border-border bg-muted p-4 text-sm text-muted-foreground">
                  <CheckCircle2
                    className="h-4 w-4 shrink-0 text-muted-foreground"
                    aria-hidden="true"
                  />
                  <span>
                    No standards fell below {k.threshold_pct} in {resolvedSession}
                    . Students met the bar across every assessment in scope.
                  </span>
                </div>
              ) : (
                <TopFocusStrip rows={data.top_focus} />
              )}
            </div>
          </div>

          <div className="mb-2 flex justify-end print:hidden">
            <div
              role="group"
              aria-label="Standard visibility"
              className="inline-flex items-center gap-1 rounded-md bg-muted/50 p-1"
            >
              <Button
                size="sm"
                variant={flaggedOnly ? 'default' : 'ghost'}
                aria-pressed={flaggedOnly}
                onClick={() => setFlaggedOnly(true)}
              >
                Flagged only
              </Button>
              <Button
                size="sm"
                variant={!flaggedOnly ? 'default' : 'ghost'}
                aria-pressed={!flaggedOnly}
                onClick={() => setFlaggedOnly(false)}
              >
                All standards
              </Button>
            </div>
          </div>

          <div className="flex flex-col gap-4">
            {data.periods.map((period, i) => (
              <PeriodSection
                key={`${period.period}-${i}`}
                period={period}
                flaggedOnly={flaggedOnly}
              />
            ))}
          </div>
        </>
      )}
    </>
  );
}
