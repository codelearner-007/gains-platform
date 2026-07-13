'use client';

import type { LucideIcon } from 'lucide-react';
import { Skeleton } from '@/components/ui/skeleton';

interface StatCardProps {
  label: string;
  value: React.ReactNode;
  hint?: string;
  icon?: LucideIcon;
  loading?: boolean;
  /**
   * `default` — icon chip + label-above-value (reports / admin strips).
   * `plain` — no icon, value-first, sentence-case wrapping label; the
   *   dashboard KPI look. Never truncates.
   */
  variant?: 'default' | 'plain';
  /** Extra classes for the value (e.g. a perf tone on Grade Average). */
  valueClassName?: string;
}

/**
 * Compact KPI card for the app dashboards. Reused by the reports stat strip,
 * the admin home and the assessment dashboard so the surfaces read as one
 * design system.
 */
export function StatCard({
  label,
  value,
  hint,
  icon: Icon,
  loading,
  variant = 'default',
  valueClassName = '',
}: StatCardProps) {
  if (variant === 'plain') {
    // Value-first, no icon, full sentence-case label — sized so the five
    // dashboard KPIs never truncate at any breakpoint. Elevated so the strip
    // reads as surfaces floating on the page, not flat outlines.
    return (
      <div className="rounded-lg border border-border bg-card px-4 py-3 shadow-sm">
        {loading ? (
          <Skeleton className="h-7 w-16" />
        ) : (
          <p
            className={`text-2xl font-semibold leading-none tabular-nums ${valueClassName || 'text-foreground'}`}
          >
            {value}
          </p>
        )}
        <p className="mt-1.5 text-xs font-medium text-muted-foreground">{label}</p>
        {hint && !loading && (
          <p className="mt-0.5 text-[11px] text-muted-foreground/80">{hint}</p>
        )}
      </div>
    );
  }

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
