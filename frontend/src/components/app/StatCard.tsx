'use client';

import type { LucideIcon } from 'lucide-react';
import { Skeleton } from '@/components/ui/skeleton';

interface StatCardProps {
  label: string;
  value: React.ReactNode;
  hint?: string;
  icon?: LucideIcon;
  loading?: boolean;
}

/**
 * Compact KPI card for the app dashboards. Minimal, brand-consistent
 * (primary-soft icon chip + tabular figures), reused by the reports stat
 * strip and the home dashboard so the two read as one design system.
 */
export function StatCard({ label, value, hint, icon: Icon, loading }: StatCardProps) {
  return (
    <div className="flex items-center gap-3 rounded-lg border border-border bg-card px-4 py-3">
      {Icon && (
        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md bg-primary-soft text-primary">
          <Icon className="h-4 w-4" />
        </div>
      )}
      <div className="min-w-0">
        <p className="truncate text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
          {label}
        </p>
        {loading ? (
          <Skeleton className="mt-1 h-6 w-12" />
        ) : (
          <p className="truncate text-xl font-semibold leading-tight tabular-nums text-foreground">
            {value}
          </p>
        )}
        {hint && !loading && (
          <p className="truncate text-[11px] text-muted-foreground">{hint}</p>
        )}
      </div>
    </div>
  );
}
