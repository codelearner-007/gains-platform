'use client';

import { useEffect } from 'react';
import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import { useQuery } from '@tanstack/react-query';
import { reportsApi, reportsKeys } from '@/lib/reports/api-client';
import ReportCanvas from '@/components/app/modules/reports/shared/ReportCanvas';
import ReportBreadcrumb, {
  assessmentCrumbs,
} from '@/components/app/modules/reports/shared/ReportBreadcrumb';
import LoadingState from '@/components/app/modules/reports/shared/LoadingState';
import ErrorState from '@/components/app/modules/reports/shared/ErrorState';
import PaginatedReportHeader from '@/components/app/modules/reports/paginated/PaginatedReportHeader';
import PaginatedKpiStrip from '@/components/app/modules/reports/paginated/PaginatedKpiStrip';
import PaginatedFooter from '@/components/app/modules/reports/paginated/PaginatedFooter';
import QuestionSummaryMatrix from '@/components/app/modules/reports/paginated/QuestionSummaryMatrix';
import { useSelectedSchool } from '@/lib/context/SelectedSchoolContext';

type Variant = 'base' | 'teacher_subtotal' | 'header_highlights';

const VARIANT_LABEL: Record<Variant, string> = {
  base: 'Question Summary Report',
  teacher_subtotal: 'Question Summary Report — Teacher Subtotal',
  header_highlights: 'Question Summary Report — Header Highlights',
};

const VARIANT_SUBTITLE: Record<Variant, string | undefined> = {
  base: undefined,
  teacher_subtotal: 'With per-teacher subtotal rows',
  header_highlights: 'Per-standard headers colored by performance band',
};

function parseVariant(raw: string | null): Variant {
  if (raw === 'teacher_subtotal' || raw === 'header_highlights') return raw;
  return 'base';
}

export default function QuestionSummaryPaginatedPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const itemId = searchParams.get('item_id');
  const variant = parseVariant(searchParams.get('variant'));

  useEffect(() => {
    if (!itemId) router.replace('/app/reports');
  }, [itemId, router]);

  const { schoolId } = useSelectedSchool();

  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: reportsKeys.questionSummaryPaginated(itemId ?? '', schoolId ?? undefined),
    queryFn: () =>
      reportsApi.questionSummaryPaginated(itemId as string, schoolId ?? undefined),
    enabled: !!itemId,
  });

  if (!itemId) return null;
  if (isLoading) return <LoadingState label="Loading question summary…" />;
  if (isError) {
    return (
      <ErrorState
        message={
          error instanceof Error ? error.message : 'Could not load report.'
        }
        onRetry={() => void refetch()}
      />
    );
  }
  if (!data) return null;

  return (
    <ReportCanvas>
      <div className="mb-3 flex flex-col gap-2 print:hidden">
        <ReportBreadcrumb
          crumbs={assessmentCrumbs({
            label: data.assessment.item_name || data.assessment.item_id,
          })}
        />
        <VariantTabs itemId={itemId} active={variant} />
      </div>

      <div className="mb-2">
        <PaginatedReportHeader
          assessment={data.assessment}
          title={VARIANT_LABEL[variant]}
          subtitle={VARIANT_SUBTITLE[variant]}
        />
      </div>

      <div className="mb-2">
        <PaginatedKpiStrip kpis={data.kpis} />
      </div>

      <QuestionSummaryMatrix
        payload={data}
        showTeacherSubtotal={variant === 'teacher_subtotal'}
        highlightStandardHeader={variant === 'header_highlights'}
      />

      <PaginatedFooter />
    </ReportCanvas>
  );
}

function VariantTabs({
  itemId,
  active,
}: {
  itemId: string;
  active: Variant;
}) {
  const variants: { slug: Variant; label: string }[] = [
    { slug: 'base', label: 'Base' },
    { slug: 'teacher_subtotal', label: 'Teacher Subtotal' },
    { slug: 'header_highlights', label: 'Header Highlights' },
  ];
  return (
    <div role="tablist" className="flex gap-1 rounded-md bg-muted/50 p-1 w-fit">
      {variants.map((v) => {
        const query: Record<string, string> = { item_id: itemId };
        if (v.slug !== 'base') query.variant = v.slug;
        return (
          <Link
            key={v.slug}
            href={{
              pathname: '/app/reports/question-summary-paginated',
              query,
            }}
            scroll={false}
            role="tab"
            aria-selected={active === v.slug}
            className={`px-3 py-1.5 text-sm rounded transition-colors ${
              active === v.slug
                ? 'bg-card text-primary shadow-sm font-medium'
                : 'text-muted-foreground hover:bg-accent hover:text-foreground'
            }`}
          >
            {v.label}
          </Link>
        );
      })}
    </div>
  );
}
