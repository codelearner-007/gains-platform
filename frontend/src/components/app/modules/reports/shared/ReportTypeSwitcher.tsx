'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import {
  getReportsByGroup,
  getAssessmentFamilyTabs,
  getFamilyByPathname,
  isReportActive,
  buildHref,
} from '@/lib/reports/report-types';
import { TAB_BASE as TAB_PILL_BASE, TAB_ACTIVE, TAB_INACTIVE } from './tabStyles';

/**
 * Top-level report-type navigation (one row of "family" tabs).
 *
 *   • Assessment group → 3 family tabs: Question Response Analysis /
 *     Standards Deep Dive / Question Summary. The QRA tab stays active across
 *     all four of its routes; its renderings live in the contextual
 *     `ReportSubTabs` row beneath. The IAD drill-through has no family tab —
 *     it is reached only by clicking a question.
 *   • Program group → one inline tab per program report.
 *
 * No overflow/"More reports" menu: every report is reachable via a family tab
 * plus (for QRA/QSR) its sub-tab row. Names, routes and icons all come from the
 * report-types registry so this can never drift from the launch menu/headers.
 */

// Family/program tabs render a leading icon, so they prepend the flex layout
// to the shared pill base (same treatment the sub-tabs use).
const TAB = `inline-flex items-center gap-1.5 ${TAB_PILL_BASE}`;

type Props =
  | {
      group: 'assessment';
      /** Required so every link preserves the assessment context. */
      itemId: string;
    }
  | { group: 'program' };

export default function ReportTypeSwitcher(props: Props) {
  const pathname = usePathname();

  if (props.group === 'assessment') {
    const { itemId } = props;
    const activeFamily = getFamilyByPathname(pathname);
    return (
      <div
        role="tablist"
        aria-label="Assessment report types"
        className="flex flex-wrap items-center gap-1 rounded-md bg-muted/50 p-1 w-fit max-w-full"
      >
        {getAssessmentFamilyTabs().map((t) => {
          const Icon = t.icon;
          const active = activeFamily === t.family;
          return (
            <Link
              key={t.family}
              href={buildHref(t.defaultSlug, { item_id: itemId })}
              role="tab"
              aria-selected={active}
              aria-current={active ? 'page' : undefined}
              title={t.fullName}
              className={`${TAB} ${active ? TAB_ACTIVE : TAB_INACTIVE}`}
            >
              <Icon className="h-3.5 w-3.5" />
              <span>{t.label}</span>
            </Link>
          );
        })}
      </div>
    );
  }

  // Program group: a flat inline tab per program report.
  return (
    <div
      role="tablist"
      aria-label="Program report types"
      className="flex flex-wrap items-center gap-1 rounded-md bg-muted/50 p-1 w-fit max-w-full"
    >
      {getReportsByGroup('program').map((r) => {
        const Icon = r.icon;
        const active = isReportActive(pathname, r.slug);
        return (
          <Link
            key={r.slug}
            href={buildHref(r.slug)}
            role="tab"
            aria-selected={active}
            aria-current={active ? 'page' : undefined}
            title={r.canonicalName}
            className={`${TAB} ${active ? TAB_ACTIVE : TAB_INACTIVE}`}
          >
            <Icon className="h-3.5 w-3.5" />
            <span>{r.shortName}</span>
          </Link>
        );
      })}
    </div>
  );
}
