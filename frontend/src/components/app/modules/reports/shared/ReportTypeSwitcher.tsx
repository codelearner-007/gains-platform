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
  type LucideIcon,
} from 'lucide-react';

type AssessmentReportSlug =
  | 'question-response-analysis'
  | 'standards-deep-dive'
  | 'incorrect-answer-details';

type ProgramReportSlug =
  | 'year-to-date-performance'
  | 'standard-summary'
  | 'strand-summary';

interface AssessmentTab {
  slug: AssessmentReportSlug;
  label: string;
  shortLabel: string;
  icon: LucideIcon;
}

interface ProgramTab {
  slug: ProgramReportSlug;
  label: string;
  shortLabel: string;
  icon: LucideIcon;
}

const ASSESSMENT_TABS: AssessmentTab[] = [
  {
    slug: 'question-response-analysis',
    label: 'Question Response',
    shortLabel: 'QRA',
    icon: FileBarChart,
  },
  {
    slug: 'standards-deep-dive',
    label: 'Standards Deep Dive',
    shortLabel: 'SDD',
    icon: Layers,
  },
];

const IAD_TAB: AssessmentTab = {
  slug: 'incorrect-answer-details',
  label: 'Incorrect Answers',
  shortLabel: 'IAD',
  icon: ListChecks,
};

const PROGRAM_TABS: ProgramTab[] = [
  {
    slug: 'year-to-date-performance',
    label: 'Year-To-Date Performance',
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

  const tabs: AssessmentTab[] =
    props.group === 'assessment'
      ? // Show IAD as a tab only when the user is currently on IAD — it is
        // otherwise only reachable as a per-question drill-through from QRA.
        pathname.endsWith('/incorrect-answer-details')
        ? [...ASSESSMENT_TABS, IAD_TAB]
        : ASSESSMENT_TABS
      : [];

  const programTabs: ProgramTab[] =
    props.group === 'program' ? PROGRAM_TABS : [];

  return (
    <div
      role="tablist"
      aria-label={
        props.group === 'assessment'
          ? 'Assessment report types'
          : 'Program report types'
      }
      className="flex flex-wrap items-center gap-1 rounded-md bg-muted/50 p-1 w-fit max-w-full"
    >
      {props.group === 'assessment'
        ? tabs.map((tab) => {
            const href = buildAssessmentHref(tab.slug, props.itemId, props.questionId);
            const active = pathname.endsWith(`/${tab.slug}`);
            // IAD tab is only "navigable" via the QRA question table; when
            // visible in the switcher it represents the current page and is
            // intentionally non-interactive on other tabs.
            const isDrillThroughOnly = tab.slug === 'incorrect-answer-details';
            return (
              <SwitcherChip
                key={tab.slug}
                href={isDrillThroughOnly ? undefined : href}
                active={active}
                icon={tab.icon}
                label={tab.label}
                shortLabel={tab.shortLabel}
              />
            );
          })
        : programTabs.map((tab) => {
            const active = pathname.endsWith(`/${tab.slug}`);
            return (
              <SwitcherChip
                key={tab.slug}
                href={`/app/reports/${tab.slug}`}
                active={active}
                icon={tab.icon}
                label={tab.label}
                shortLabel={tab.shortLabel}
              />
            );
          })}
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
