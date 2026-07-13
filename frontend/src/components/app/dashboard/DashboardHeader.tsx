'use client';

import type { ReactNode } from 'react';
import { GraduationCap } from 'lucide-react';
import { Skeleton } from '@/components/ui/skeleton';

interface DashboardHeaderProps {
  schoolName: string | null;
  logoUrl: string | null;
  currentSession: string | null;
  loading: boolean;
  /** Page-scoped actions (e.g. the Filters popover), rendered top-right. */
  actions?: ReactNode;
}

/**
 * "Assessment Analysis Dashboard" page header: school logo + name on the left,
 * the report title, and the Academic Year + page actions on the right. A plain
 * hairline-separated header (no coloured band) — hierarchy comes from type and
 * spacing, not chrome.
 */
export default function DashboardHeader({
  schoolName,
  logoUrl,
  currentSession,
  loading,
  actions,
}: DashboardHeaderProps) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-x-6 gap-y-3 border-b border-border pb-5">
      <div className="flex items-center gap-3">
        {logoUrl ? (
          // eslint-disable-next-line @next/next/no-img-element -- tenant logo is an arbitrary external/storage URL; no Next image domain config
          <img
            src={logoUrl}
            alt={schoolName ? `${schoolName} logo` : 'School logo'}
            className="h-10 w-10 shrink-0 rounded-md border border-border bg-card object-contain p-1"
          />
        ) : (
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-md border border-border bg-card text-muted-foreground">
            <GraduationCap className="h-5 w-5" />
          </div>
        )}
        <div className="min-w-0">
          <h1 className="text-xl font-semibold tracking-tight text-foreground">
            Assessment Analysis Dashboard
          </h1>
          {loading ? (
            <Skeleton className="mt-1 h-4 w-40" />
          ) : (
            <p className="text-sm text-muted-foreground">
              {schoolName ?? 'Select a school'}
            </p>
          )}
        </div>
      </div>

      <div className="flex items-center gap-4">
        <div className="text-right">
          <p className="text-xs text-muted-foreground">Academic Year</p>
          {loading ? (
            <Skeleton className="mt-1 h-4 w-16" />
          ) : (
            <p className="text-sm font-semibold tabular-nums text-foreground">
              {currentSession || '—'}
            </p>
          )}
        </div>
        {actions}
      </div>
    </div>
  );
}
