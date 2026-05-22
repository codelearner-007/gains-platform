import Link from 'next/link';
import {
  ArrowUpRight,
  GraduationCap,
  LineChart,
  Network,
} from 'lucide-react';
import AssessmentBrowser from '@/components/app/modules/reports/AssessmentBrowser';

export const metadata = {
  title: 'Reports',
};

const PROGRAM_REPORTS = [
  {
    href: '/app/reports/year-to-date-performance',
    title: 'Year To Date - Longitudinal Report',
    description:
      'Trend, grade distribution, strand heat-map, and most-improved/dropped students for the current session.',
    icon: LineChart,
  },
  {
    href: '/app/reports/standard-summary',
    title: 'Standard Summary',
    description:
      'School-wide standards rollup with per-standard performance, grouped by strand.',
    icon: GraduationCap,
  },
  {
    href: '/app/reports/strand-summary',
    title: 'Strand Summary',
    description:
      'School-wide strand rollup with treemap, performance bands, and per-standard drill-down.',
    icon: Network,
  },
] as const;

export default function ReportsLandingPage() {
  return (
    <div className="max-w-6xl mx-auto space-y-10">
      <header className="space-y-1">
        <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
          Reports
        </p>
        <h1 className="text-2xl font-semibold tracking-tight text-foreground">
          Pick a report
        </h1>
        <p className="text-sm text-muted-foreground max-w-2xl">
          Assessment Reports are scoped to a single assessment you select below.
          Program Reports cover the whole school or session.
        </p>
      </header>

      <section aria-labelledby="assessment-reports-heading" className="space-y-4">
        <div className="flex items-baseline justify-between gap-3">
          <div className="space-y-1">
            <h2
              id="assessment-reports-heading"
              className="text-base font-semibold tracking-tight text-foreground"
            >
              Assessment Reports
            </h2>
            <p className="text-xs text-muted-foreground">
              Pick an assessment, then open a report.
            </p>
          </div>
        </div>

        <AssessmentBrowser />
      </section>

      <section aria-labelledby="program-reports-heading" className="space-y-4">
        <div className="space-y-1">
          <h2
            id="program-reports-heading"
            className="text-base font-semibold tracking-tight text-foreground"
          >
            Program Reports
          </h2>
          <p className="text-xs text-muted-foreground">
            School- and year-wide views. No assessment selection needed.
          </p>
        </div>

        <ul className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {PROGRAM_REPORTS.map((report) => {
            const Icon = report.icon;
            return (
              <li key={report.href}>
                <Link
                  href={report.href}
                  className="group block h-full bg-card border border-border rounded-lg p-4 hover:border-foreground/20 hover:shadow-sm transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="h-8 w-8 rounded-md bg-primary-soft text-primary flex items-center justify-center shrink-0">
                      <Icon className="h-4 w-4" />
                    </div>
                    <ArrowUpRight className="h-4 w-4 text-muted-foreground/50 group-hover:text-primary transition-colors" />
                  </div>
                  <h3 className="mt-3 text-sm font-semibold text-foreground">
                    {report.title}
                  </h3>
                  <p className="mt-1 text-xs text-muted-foreground leading-relaxed">
                    {report.description}
                  </p>
                </Link>
              </li>
            );
          })}
        </ul>
      </section>
    </div>
  );
}
