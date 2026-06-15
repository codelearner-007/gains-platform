'use client';

import { GraduationCap } from 'lucide-react';
import { HEADER_BAR_BG, LAYOUT_BORDER } from '@/lib/reports/colors';
import { Skeleton } from '@/components/ui/skeleton';

interface DashboardHeaderProps {
  schoolName: string | null;
  logoUrl: string | null;
  currentSession: string | null;
  loading: boolean;
}

/**
 * Legacy "Assessment Analysis Dashboard" header band: school logo + name on the
 * left, the report title centre-left, and the Academic Year on the right —
 * faithful to PBIX "Home" (SchoolLogo_Parameter + Titles.__Title + Session).
 */
export default function DashboardHeader({
  schoolName,
  logoUrl,
  currentSession,
  loading,
}: DashboardHeaderProps) {
  return (
    <div
      className="flex flex-wrap items-center justify-between gap-3 rounded-lg border px-4 py-3"
      style={{ backgroundColor: HEADER_BAR_BG, borderColor: LAYOUT_BORDER }}
    >
      <div className="flex items-center gap-3">
        {logoUrl ? (
          // eslint-disable-next-line @next/next/no-img-element -- tenant logo is an arbitrary external/storage URL; no Next image domain config
          <img
            src={logoUrl}
            alt={schoolName ? `${schoolName} logo` : 'School logo'}
            className="h-11 w-11 shrink-0 rounded-md bg-white object-contain p-0.5"
          />
        ) : (
          <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-md bg-white/70 text-primary">
            <GraduationCap className="h-6 w-6" />
          </div>
        )}
        <div className="min-w-0">
          <h1 className="truncate text-lg font-bold leading-tight text-foreground">
            Assessment Analysis Dashboard
          </h1>
          {loading ? (
            <Skeleton className="mt-1 h-4 w-40" />
          ) : (
            <p className="truncate text-sm text-foreground/70">
              {schoolName ?? 'Select a school'}
            </p>
          )}
        </div>
      </div>

      <div className="flex items-center gap-2">
        <span className="text-xs font-medium uppercase tracking-wider text-foreground/70">
          Academic Year
        </span>
        {loading ? (
          <Skeleton className="h-6 w-20" />
        ) : (
          <span
            className="rounded-md border bg-white px-3 py-1 text-sm font-semibold tabular-nums text-foreground"
            style={{ borderColor: LAYOUT_BORDER }}
          >
            {currentSession || '—'}
          </span>
        )}
      </div>
    </div>
  );
}
