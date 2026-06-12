'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { ChevronDown, MoreHorizontal, type LucideIcon } from 'lucide-react';
import {
  REPORT_TYPES,
  getReportsByGroup,
  getReportByPathname,
  isReportActive,
  buildHref,
  type ReportType,
  type ReportGroup,
  type ReportKind,
  type ReportSlug,
} from '@/lib/reports/report-types';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import {
  TAB_BASE as TAB_PILL_BASE,
  TAB_ACTIVE,
  TAB_INACTIVE,
} from './tabStyles';

/**
 * Adaptive report-type navigation.
 *
 * Every report in a family is reachable from every other member of that
 * family. The switcher stays a single row at any report count:
 *
 *   • Wide viewports — the top `INLINE_COUNT` priority siblings render as
 *     inline tabs; the remainder live in a grouped "More reports" dropdown.
 *   • Narrow viewports — collapses to a single dropdown trigger that shows
 *     the current report's name.
 *
 * Names, routes, icons, and grouping all come from the report-types
 * registry, so this can never disagree with the launch menu or page headers.
 */

const INLINE_COUNT = 3;

/** Order + labels for the grouped sections inside the overflow menu. */
const KIND_LABELS: Record<ReportKind, string> = {
  interactive: 'Interactive',
  paginated: 'Paginated & Print',
  drilldown: 'Drill-through',
};
const KIND_ORDER: ReportKind[] = ['interactive', 'paginated', 'drilldown'];

type Props =
  | {
      group: 'assessment';
      /** Required so every link preserves the assessment context. */
      itemId: string;
      /** Question id — only set on the IAD drill-through page. */
      questionId?: string | null;
    }
  | { group: 'program' };

export default function ReportTypeSwitcher(props: Props) {
  const pathname = usePathname();
  const reports = getReportsByGroup(props.group);
  const sorted = [...reports].sort((a, b) => a.priority - b.priority);

  const itemId = props.group === 'assessment' ? props.itemId : undefined;
  const questionId =
    props.group === 'assessment' ? props.questionId ?? null : null;

  const current =
    getReportByPathname(pathname) ??
    sorted.find((r) => r.group === props.group) ??
    sorted[0];

  const hrefFor = (slug: ReportSlug) =>
    buildHref(slug, { item_id: itemId, question_id: questionId });

  /**
   * A drill-through report (IAD) is only navigable with a question context.
   * Without one it appears in the menu but disabled, with a hint tooltip.
   */
  const isReachable = (r: ReportType) =>
    r.kind !== 'drilldown' || !!questionId || isReportActive(pathname, r.slug);

  const inline = sorted.slice(0, INLINE_COUNT);
  const overflow = sorted.slice(INLINE_COUNT);

  const groupLabel =
    props.group === 'assessment'
      ? 'Assessment report types'
      : 'Program report types';

  return (
    <TooltipProvider delayDuration={200}>
      {/* Narrow viewport: a single dropdown labelled with the current report. */}
      <div className="sm:hidden">
        <MoreReportsMenu
          label={groupLabel}
          reports={sorted}
          pathname={pathname}
          hrefFor={hrefFor}
          isReachable={isReachable}
          triggerVariant="single"
          currentName={current?.canonicalName ?? 'Reports'}
        />
      </div>

      {/* Wide viewport: inline tabs + grouped overflow menu. */}
      <div
        role="tablist"
        aria-label={groupLabel}
        className="hidden sm:flex items-center gap-1 rounded-md bg-muted/50 p-1 w-fit max-w-full"
      >
        {inline.map((r) => (
          <InlineTab
            key={r.slug}
            report={r}
            active={isReportActive(pathname, r.slug)}
            href={isReachable(r) ? hrefFor(r.slug) : undefined}
          />
        ))}

        {overflow.length > 0 && (
          <MoreReportsMenu
            label={groupLabel}
            reports={overflow}
            pathname={pathname}
            hrefFor={hrefFor}
            isReachable={isReachable}
            triggerVariant="more"
          />
        )}
      </div>
    </TooltipProvider>
  );
}

// Inline tabs carry a leading icon, so they prepend the flex layout to the
// shared pill base. Active/inactive states are the shared constants verbatim.
const TAB_BASE = `inline-flex items-center gap-1.5 ${TAB_PILL_BASE}`;

function InlineTab({
  report,
  active,
  href,
}: {
  report: ReportType;
  active: boolean;
  href?: ReturnType<typeof buildHref>;
}) {
  const Icon = report.icon;

  if (!href) {
    return (
      <span
        role="tab"
        aria-selected={active}
        aria-disabled={!active}
        className={`${TAB_BASE} ${active ? TAB_ACTIVE : 'text-muted-foreground/60 cursor-default'}`}
      >
        <Icon className="h-3.5 w-3.5" />
        <span>{report.shortName}</span>
      </span>
    );
  }

  return (
    <Link
      href={href}
      role="tab"
      aria-selected={active}
      aria-current={active ? 'page' : undefined}
      className={`${TAB_BASE} ${active ? TAB_ACTIVE : TAB_INACTIVE}`}
    >
      <Icon className="h-3.5 w-3.5" />
      <span>{report.shortName}</span>
    </Link>
  );
}

function MoreReportsMenu({
  label,
  reports,
  pathname,
  hrefFor,
  isReachable,
  triggerVariant,
  currentName,
}: {
  label: string;
  reports: ReportType[];
  pathname: string;
  hrefFor: (slug: ReportSlug) => ReturnType<typeof buildHref>;
  isReachable: (r: ReportType) => boolean;
  triggerVariant: 'more' | 'single';
  currentName?: string;
}) {
  // Group the menu entries by kind, preserving the canonical kind order.
  const groups = KIND_ORDER.map((kind) => ({
    kind,
    items: reports.filter((r) => r.kind === kind),
  })).filter((g) => g.items.length > 0);

  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        className={
          triggerVariant === 'single'
            ? 'inline-flex w-full items-center justify-between gap-1.5 rounded-md border border-border bg-muted/50 px-3 py-1.5 text-sm font-medium text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring'
            : `${TAB_BASE} ${TAB_INACTIVE}`
        }
        aria-label={triggerVariant === 'single' ? label : 'More reports'}
      >
        {triggerVariant === 'single' ? (
          <>
            <span className="truncate">{currentName}</span>
            <ChevronDown className="h-4 w-4 shrink-0 text-muted-foreground" />
          </>
        ) : (
          <>
            <MoreHorizontal className="h-3.5 w-3.5" />
            <span>More reports</span>
            <ChevronDown className="h-3.5 w-3.5 text-muted-foreground" />
          </>
        )}
      </DropdownMenuTrigger>

      <DropdownMenuContent align="start" className="w-72">
        {groups.map((g, gi) => (
          <DropdownMenuGroup key={g.kind}>
            {gi > 0 && <DropdownMenuSeparator />}
            <DropdownMenuLabel className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
              {KIND_LABELS[g.kind]}
            </DropdownMenuLabel>
            {g.items.map((r) => (
              <MenuRow
                key={r.slug}
                report={r}
                active={isReportActive(pathname, r.slug)}
                href={isReachable(r) ? hrefFor(r.slug) : undefined}
              />
            ))}
          </DropdownMenuGroup>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

function MenuRow({
  report,
  active,
  href,
}: {
  report: ReportType;
  active: boolean;
  href?: ReturnType<typeof buildHref>;
}) {
  const Icon: LucideIcon = report.icon;

  // Drill-through without a question context: a disabled item + hint tooltip.
  if (!href) {
    return (
      <Tooltip>
        <TooltipTrigger asChild>
          <DropdownMenuItem
            disabled
            className="cursor-default"
            aria-current={active ? 'page' : undefined}
          >
            <Icon className="h-4 w-4 text-muted-foreground" />
            <span className="flex-1 truncate">{report.canonicalName}</span>
          </DropdownMenuItem>
        </TooltipTrigger>
        <TooltipContent side="right">Open from a question</TooltipContent>
      </Tooltip>
    );
  }

  return (
    <DropdownMenuItem asChild>
      <Link
        href={href}
        aria-current={active ? 'page' : undefined}
        className={`cursor-pointer ${active ? 'font-medium text-primary' : ''}`}
      >
        <Icon
          className={`h-4 w-4 ${active ? 'text-primary' : 'text-muted-foreground'}`}
        />
        <span className="flex-1 truncate">{report.canonicalName}</span>
        {active && (
          <span className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
            Current
          </span>
        )}
      </Link>
    </DropdownMenuItem>
  );
}

// Re-export so callers that only need the registry don't import two modules.
export { REPORT_TYPES };
export type { ReportGroup };
