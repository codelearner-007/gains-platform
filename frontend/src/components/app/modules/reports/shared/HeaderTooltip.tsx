'use client';

import * as React from 'react';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import { cn } from '@/lib/utils/index';

interface ColumnTooltipProps {
  /** The full, proper column name (bold first line of the tooltip). */
  title: string;
  /** Optional one-line plain-English description of what the column means. */
  description?: string;
  /** Tooltip side. Header rows live at the top of a table, so default below. */
  side?: 'top' | 'right' | 'bottom' | 'left';
  /** The focusable trigger element, rendered via Radix `asChild`. */
  children: React.ReactElement;
}

/**
 * Shared tooltip shell for report column headers: an immediate
 * (`delayDuration={0}`), keyboard-reachable tooltip whose body is the bold
 * `title` + optional `description`. The `children` element IS the focusable
 * trigger (rendered via Radix `asChild`). Used by `HeaderTooltip` (plain `<th>`,
 * span trigger) and `SortableHeader` (sortable button trigger) so the provider
 * config and content markup live in exactly one place.
 */
export function ColumnTooltip({
  title,
  description,
  side = 'bottom',
  children,
}: ColumnTooltipProps) {
  return (
    <TooltipProvider delayDuration={0} skipDelayDuration={0}>
      <Tooltip>
        <TooltipTrigger asChild>{children}</TooltipTrigger>
        <TooltipContent side={side} className="max-w-[260px]">
          <p className="font-semibold leading-snug">{title}</p>
          {description ? (
            <p className="mt-0.5 text-xs leading-snug text-muted-foreground">
              {description}
            </p>
          ) : null}
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}

interface HeaderTooltipProps {
  /** The full, proper column name (bold first line of the tooltip). */
  title: string;
  /** Optional one-line plain-English description of what the column means. */
  description?: string;
  /**
   * The visible header content. Defaults to `title`. Pass the (possibly
   * abbreviated / truncated) on-screen label here — e.g. "#St" — while `title`
   * carries the full name ("# Students").
   */
  children?: React.ReactNode;
  /** Tooltip side. Header rows live at the top of a table, so default below. */
  side?: 'top' | 'right' | 'bottom' | 'left';
  /** Extra classes for the focusable trigger span. */
  className?: string;
}

/**
 * Accessible column-header tooltip for report tables (GAI-19).
 *
 * Wraps a (usually truncated/abbreviated) header label and reveals the full
 * column name + a short description on hover OR keyboard focus, appearing
 * IMMEDIATELY (`delayDuration={0}`). The trigger is a focusable `<span>` so the
 * tooltip is keyboard-reachable and not hover-only (WCAG / skill `tooltip-keyboard`).
 *
 * Use this for PLAIN `<th>` headers. Sortable headers carry their own tooltip
 * via `SortableHeader`'s `title`/`description` props (the button is the trigger).
 */
export default function HeaderTooltip({
  title,
  description,
  children,
  side = 'bottom',
  className,
}: HeaderTooltipProps) {
  return (
    <ColumnTooltip title={title} description={description} side={side}>
      <span
        tabIndex={0}
        className={cn(
          'inline-flex min-w-0 max-w-full cursor-help items-center truncate align-middle outline-none focus-visible:ring-2 focus-visible:ring-ring',
          className,
        )}
      >
        {children ?? title}
      </span>
    </ColumnTooltip>
  );
}
