'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import {
  getReportsByFamily,
  isReportActive,
  buildHref,
  type ReportFamily,
} from '@/lib/reports/report-types';
import { TAB_BASE, TAB_ACTIVE, TAB_INACTIVE } from './tabStyles';

/**
 * Contextual sub-tab row for an assessment family that has several renderings
 * of the same report behind DIFFERENT routes (currently Question Response
 * Analysis: an Interactive view + three printable cuts). Styled to match the
 * QSR `ReportVariantTabs` row exactly — plain text pills, no icons, no group
 * labels — but each tab is a route link rather than a `?variant` change. The
 * per-rendering label comes from the registry (`subTabLabel`, fallback
 * `shortName`).
 */

export default function ReportSubTabs({
  family,
  itemId,
}: {
  family: ReportFamily;
  itemId: string;
}) {
  const pathname = usePathname();
  const reports = getReportsByFamily(family);
  // A single-rendering family (e.g. SDD) has no sub-tabs.
  if (reports.length <= 1) return null;

  return (
    <div
      role="tablist"
      aria-label="Report rendering"
      className="flex flex-wrap gap-1 rounded-md bg-muted/50 p-1 w-fit max-w-full"
    >
      {reports.map((r) => {
        const active = isReportActive(pathname, r.slug);
        return (
          <Link
            key={r.slug}
            href={buildHref(r.slug, { item_id: itemId })}
            role="tab"
            aria-selected={active}
            aria-current={active ? 'page' : undefined}
            className={`${TAB_BASE} ${active ? TAB_ACTIVE : TAB_INACTIVE}`}
          >
            {r.subTabLabel ?? r.shortName}
          </Link>
        );
      })}
    </div>
  );
}
