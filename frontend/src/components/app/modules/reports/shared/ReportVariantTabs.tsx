'use client';

import Link from 'next/link';

/**
 * Shared variant sub-toggle for reports that have multiple renderings of the
 * same data behind a `?variant=` query (e.g. the QSR Base / Teacher / Redacted
 * cuts). Sits beneath the ReportTypeSwitcher and never changes the route, only
 * the variant query, so deep links and the back button keep working.
 */

export interface VariantOption<V extends string> {
  /** Variant value; the default variant should omit `?variant` from the URL. */
  value: V;
  label: string;
}

interface Props<V extends string> {
  /** Route these variants live under, e.g. /app/reports/question-summary-paginated. */
  pathname: string;
  /** Query params carried on every variant link (e.g. item_id). */
  baseQuery: Record<string, string>;
  options: VariantOption<V>[];
  /** Currently selected variant. */
  active: V;
  /** The variant value that represents "no `?variant` param" (the default cut). */
  defaultValue: V;
  /** Accessible label for the tablist. */
  ariaLabel?: string;
}

export default function ReportVariantTabs<V extends string>({
  pathname,
  baseQuery,
  options,
  active,
  defaultValue,
  ariaLabel = 'Report variant',
}: Props<V>) {
  return (
    <div
      role="tablist"
      aria-label={ariaLabel}
      className="flex gap-1 rounded-md bg-muted/50 p-1 w-fit"
    >
      {options.map((opt) => {
        const query: Record<string, string> = { ...baseQuery };
        if (opt.value !== defaultValue) query.variant = opt.value;
        const isActive = active === opt.value;
        return (
          <Link
            key={opt.value}
            href={{ pathname, query }}
            scroll={false}
            role="tab"
            aria-selected={isActive}
            aria-current={isActive ? 'page' : undefined}
            className={`px-3 py-1.5 text-sm rounded transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${
              isActive
                ? 'bg-card text-primary shadow-sm font-medium'
                : 'text-muted-foreground hover:bg-accent hover:text-foreground'
            }`}
          >
            {opt.label}
          </Link>
        );
      })}
    </div>
  );
}
