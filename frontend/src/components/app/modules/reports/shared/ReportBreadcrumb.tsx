import Link from 'next/link';
import { ChevronRight } from 'lucide-react';

export interface BreadcrumbCrumb {
  label: string;
  href?: string;
}

interface Props {
  crumbs: BreadcrumbCrumb[];
}

const REPORTS_HREF = '/app/reports';

export function assessmentCrumbs(
  item: BreadcrumbCrumb,
  trailing?: BreadcrumbCrumb,
): BreadcrumbCrumb[] {
  const base: BreadcrumbCrumb[] = [
    { label: 'Reports', href: REPORTS_HREF },
    { label: 'Assessment Reports', href: REPORTS_HREF },
    item,
  ];
  return trailing ? [...base, trailing] : base;
}

export function programCrumbs(title: string): BreadcrumbCrumb[] {
  return [
    { label: 'Reports', href: REPORTS_HREF },
    { label: 'Program Reports', href: REPORTS_HREF },
    { label: title },
  ];
}

export default function ReportBreadcrumb({ crumbs }: Props) {
  return (
    <nav
      aria-label="Breadcrumb"
      className="flex items-center text-xs text-muted-foreground"
    >
      <ol className="flex items-center gap-1 min-w-0">
        {crumbs.map((c, i) => {
          const isLast = i === crumbs.length - 1;
          return (
            <li
              key={`${c.label}-${i}`}
              className="flex items-center gap-1 min-w-0"
            >
              {i > 0 && (
                <ChevronRight
                  className="h-3 w-3 shrink-0 text-muted-foreground/60"
                  aria-hidden
                />
              )}
              {isLast || !c.href ? (
                <span
                  className="font-medium text-foreground truncate max-w-[28ch]"
                  title={c.label}
                  aria-current={isLast ? 'page' : undefined}
                >
                  {c.label}
                </span>
              ) : (
                <Link
                  href={c.href}
                  className="hover:text-foreground transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded-sm"
                >
                  {c.label}
                </Link>
              )}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
