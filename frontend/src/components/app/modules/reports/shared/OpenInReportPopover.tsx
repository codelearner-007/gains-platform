'use client';

import Link from 'next/link';
import { ExternalLink } from 'lucide-react';
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover';
import { buildHref, getReportBySlug } from '@/lib/reports/report-types';

const QRA = getReportBySlug('question-response-analysis');

/**
 * Small "open in another report" affordance used on Standards Deep Dive rows:
 * a trailing icon button that pops a single link to the interactive Question
 * Response Analysis report with the clicked strand/standard pre-applied as a
 * filter. Stops propagation so it never triggers the row's in-page cross-filter,
 * and is `print:hidden` so it stays out of exported PDFs.
 */
export default function OpenInReportPopover({
  itemId,
  strand,
  standard,
  label,
}: {
  itemId: string;
  strand?: string;
  standard?: string;
  /** Human label of the clicked value, for the accessible name. */
  label: string;
}) {
  const Icon = QRA.icon;
  return (
    <Popover>
      <PopoverTrigger asChild>
        <button
          type="button"
          onClick={(e) => e.stopPropagation()}
          onKeyDown={(e) => e.stopPropagation()}
          aria-label={`Open Question Response Analysis filtered by ${label}`}
          title="Open in Question Response Analysis"
          className="print:hidden shrink-0 inline-flex h-5 w-5 items-center justify-center rounded text-neutral-500 hover:bg-neutral-100 hover:text-blue-700 cursor-pointer"
        >
          <ExternalLink className="h-3.5 w-3.5" aria-hidden="true" />
        </button>
      </PopoverTrigger>
      <PopoverContent
        align="end"
        className="w-auto p-1"
        onClick={(e) => e.stopPropagation()}
      >
        <Link
          href={buildHref('question-response-analysis', {
            item_id: itemId,
            strand,
            standard,
          })}
          className="flex items-center gap-2 rounded px-2 py-1.5 text-[12px] font-medium text-foreground hover:bg-accent"
        >
          <Icon className="h-4 w-4 text-neutral-600" aria-hidden="true" />
          <span>Open in {QRA.canonicalName}</span>
        </Link>
      </PopoverContent>
    </Popover>
  );
}
