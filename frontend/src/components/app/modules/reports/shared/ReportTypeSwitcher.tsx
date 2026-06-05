'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import {
  FileBarChart,
  Layers,
  ListChecks,
  LineChart,
  GraduationCap,
  Network,
  Table2,
  type LucideIcon,
} from 'lucide-react';

type AssessmentReportSlug =
  | 'question-response-analysis'
  | 'standards-deep-dive'
  | 'question-summary-paginated'
  | 'question-response-analysis-paginated'
  | 'incorrect-answer-details';

type ProgramReportSlug =
  | 'year-to-date-performance'
  | 'standard-summary'
  | 'strand-summary';

interface TabDef<S extends string> {
  slug: S;
  label: string;
  shortLabel: string;
  icon: LucideIcon;
}

const ASSESSMENT_TABS: TabDef<AssessmentReportSlug>[] = [
  {
    slug: 'question-response-analysis',
    label: 'Question Response Analysis Interactive',
    shortLabel: 'QRA',
    icon: FileBarChart,
  },
  {
    slug: 'standards-deep-dive',
    label: 'Standards Deep Dive interactive',
    shortLabel: 'SDD',
    icon: Layers,
  },
  {
    slug: 'question-summary-paginated',
    label: 'Question Summary Report',
    shortLabel: 'QSR',
    icon: Table2,
  },
  {
    slug: 'question-response-analysis-paginated',
    label: 'Question Response Analysis Report',
    shortLabel: 'QRA (paginated)',
    icon: FileBarChart,
  },
];

const IAD_TAB: TabDef<AssessmentReportSlug> = {
  slug: 'incorrect-answer-details',
  label: 'Incorrect Answer Details',
  shortLabel: 'IAD',
  icon: ListChecks,
};

const PROGRAM_TABS: TabDef<ProgramReportSlug>[] = [
  {
    slug: 'year-to-date-performance',
    label: 'Year To Date - Longitudinal Report',
    shortLabel: 'YTD',
    icon: LineChart,
  },
  {
    slug: 'standard-summary',
    label: 'Standard Summary',
    shortLabel: 'Standards',
    icon: GraduationCap,
  },
  {
    slug: 'strand-summary',
    label: 'Strand Summary',
    shortLabel: 'Strands',
    icon: Network,
  },
];

type Props =
  | {
      group: 'assessment';
      /** Required for assessment tabs so the switcher preserves item context. */
      itemId: string;
      /** Question id, only set on the IAD page. */
      questionId?: string | null;
    }
  | { group: 'program' };

export default function ReportTypeSwitcher(props: Props) {
  const pathname = usePathname();

  if (props.group === 'program') {
    return (
      <SwitcherShell label="Program report types">
        {PROGRAM_TABS.map((tab) => (
          <SwitcherChip
            key={tab.slug}
            href={`/app/reports/${tab.slug}`}
            active={pathname.endsWith(`/${tab.slug}`)}
            icon={tab.icon}
            label={tab.label}
            shortLabel={tab.shortLabel}
          />
        ))}
      </SwitcherShell>
    );
  }

  // Show IAD as a tab only when the user is currently on IAD — it is
  // otherwise only reachable as a per-question drill-through from QRA.
  const onIad = pathname.endsWith('/incorrect-answer-details');
  const tabs = onIad ? [...ASSESSMENT_TABS, IAD_TAB] : ASSESSMENT_TABS;

  return (
    <SwitcherShell label="Assessment report types">
      {tabs.map((tab) => {
        // IAD tab is only "navigable" via the QRA question table; when
        // visible in the switcher it represents the current page and is
        // intentionally non-interactive on other tabs.
        const isDrillThroughOnly = tab.slug === 'incorrect-answer-details';
        return (
          <SwitcherChip
            key={tab.slug}
            href={
              isDrillThroughOnly
                ? undefined
                : buildAssessmentHref(tab.slug, props.itemId, props.questionId)
            }
            active={pathname.endsWith(`/${tab.slug}`)}
            icon={tab.icon}
            label={tab.label}
            shortLabel={tab.shortLabel}
          />
        );
      })}
    </SwitcherShell>
  );
}

function SwitcherShell({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div
      role="tablist"
      aria-label={label}
      className="flex flex-wrap items-center gap-1 rounded-md bg-muted/50 p-1 w-fit max-w-full"
    >
      {children}
    </div>
  );
}

function buildAssessmentHref(
  slug: AssessmentReportSlug,
  itemId: string,
  questionId?: string | null,
) {
  const query: Record<string, string> = { item_id: itemId };
  if (slug === 'incorrect-answer-details' && questionId) {
    query.question_id = questionId;
  }
  return { pathname: `/app/reports/${slug}`, query };
}

interface ChipProps {
  href?: string | { pathname: string; query: Record<string, string> };
  active: boolean;
  icon: LucideIcon;
  label: string;
  shortLabel: string;
}

function SwitcherChip({ href, active, icon: Icon, label, shortLabel }: ChipProps) {
  const base =
    'inline-flex items-center gap-1.5 px-3 py-1.5 text-sm rounded transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring';
  const activeCls = 'bg-card text-primary shadow-sm font-medium';
  const inactiveCls =
    'text-muted-foreground hover:bg-accent hover:text-foreground';

  if (!href) {
    return (
      <span
        role="tab"
        aria-selected={active}
        aria-disabled={!active}
        className={`${base} ${active ? activeCls : 'text-muted-foreground/60 cursor-default'}`}
      >
        <Icon className="h-3.5 w-3.5" />
        <span className="hidden sm:inline">{label}</span>
        <span className="sm:hidden">{shortLabel}</span>
      </span>
    );
  }

  return (
    <Link
      href={href}
      role="tab"
      aria-selected={active}
      className={`${base} ${active ? activeCls : inactiveCls}`}
    >
      <Icon className="h-3.5 w-3.5" />
      <span className="hidden sm:inline">{label}</span>
      <span className="sm:hidden">{shortLabel}</span>
    </Link>
  );
}
