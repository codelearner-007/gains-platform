'use client';

import { useQuery } from '@tanstack/react-query';
import { RotateCw, SlidersHorizontal } from 'lucide-react';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover';
import { reportsApi, reportsKeys } from '@/lib/reports/api-client';
import { useSelectedSchool } from '@/lib/context/SelectedSchoolContext';
import type { AssessmentFilters } from '@/lib/reports/types';

const ANY = '__any__';

interface FilterPopoverProps {
  filters: AssessmentFilters;
  onChange: (next: AssessmentFilters) => void;
  refreshedAt?: string | null;
  onRefresh: () => void;
  refreshing?: boolean;
  /** Lock the filter controls while filter-dependent data refetches. */
  disabled?: boolean;
}

/**
 * On-demand secondary-filter sub-window (legacy PowerBI filter popover):
 * Academic Year, Assessment Type, Section Instructors + a Refresh Dataset
 * button and a "last refreshed" line. Subject + grade live up front (cards /
 * chips), so they are intentionally NOT here. A count badge on the trigger
 * shows how many of these secondary filters are active.
 */
export default function FilterPopover({
  filters,
  onChange,
  refreshedAt,
  onRefresh,
  refreshing,
  disabled,
}: FilterPopoverProps) {
  const { schoolId } = useSelectedSchool();
  const sessionsQ = useQuery({
    queryKey: reportsKeys.sessions(schoolId ?? undefined),
    queryFn: () => reportsApi.sessions(schoolId ?? undefined),
  });
  const typesQ = useQuery({
    queryKey: reportsKeys.assessmentTypes(schoolId ?? undefined),
    queryFn: () => reportsApi.assessmentTypes(schoolId ?? undefined),
  });
  const instructorsQ = useQuery({
    queryKey: reportsKeys.instructors(schoolId ?? undefined),
    queryFn: () => reportsApi.instructors(schoolId ?? undefined),
  });

  function update(field: keyof AssessmentFilters, raw: string) {
    onChange({ ...filters, [field]: raw === ANY ? undefined : raw });
  }

  // The academic year is always set (a default that is never cleared), so it is
  // not counted as an "applied" secondary filter or cleared by Reset.
  const activeCount = [filters.category, filters.instructor].filter(Boolean).length;

  const sessions = sessionsQ.data ?? [];
  const types = typesQ.data ?? [];
  const instructors = instructorsQ.data ?? [];

  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button variant="outline" size="sm" className="h-9 gap-2">
          <SlidersHorizontal className="h-4 w-4" />
          <span>Filters</span>
          {activeCount > 0 && (
            <Badge className="ml-0.5 h-5 min-w-5 justify-center rounded-full px-1 tabular-nums">
              {activeCount}
            </Badge>
          )}
        </Button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-80 space-y-4">
        <FilterSelect
          label="Academic Year"
          value={filters.session ?? ANY}
          onValueChange={(v) => update('session', v)}
          options={sessions.map((s) => ({
            value: s.session ?? s.session_id,
            label: s.session ?? s.session_id,
          }))}
          allowClear={false}
          disabled={disabled}
        />
        <FilterSelect
          label="Assessment Type"
          value={filters.category ?? ANY}
          onValueChange={(v) => update('category', v)}
          options={types.map((t) => ({ value: t.assessment_type, label: t.assessment_type }))}
          disabled={disabled}
        />
        <FilterSelect
          label="Section Instructors"
          value={filters.instructor ?? ANY}
          onValueChange={(v) => update('instructor', v)}
          options={instructors.map((i) => ({ value: i.instructor, label: i.instructor }))}
          disabled={disabled}
        />

        <div className="space-y-2 border-t border-border pt-3">
          {refreshedAt && (
            <p className="text-[11px] text-muted-foreground">
              Dataset last refreshed:{' '}
              <span className="font-medium text-foreground">
                {formatRefreshed(refreshedAt)}
              </span>
            </p>
          )}
          <div className="flex items-center justify-between">
            <Button
              variant="ghost"
              size="sm"
              onClick={() =>
                // Keep the academic year (it must never be null); clear only the
                // grade-independent secondary filters.
                onChange({ ...filters, category: undefined, instructor: undefined })
              }
              disabled={disabled || activeCount === 0}
            >
              Reset
            </Button>
            <Button
              size="sm"
              onClick={onRefresh}
              disabled={disabled || refreshing}
              className="gap-2"
            >
              <RotateCw
                className={['h-3.5 w-3.5', refreshing ? 'animate-spin' : ''].join(' ')}
                aria-hidden
              />
              Refresh Dataset
            </Button>
          </div>
        </div>
      </PopoverContent>
    </Popover>
  );
}

function FilterSelect({
  label,
  value,
  onValueChange,
  options,
  disabled,
  allowClear = true,
}: {
  label: string;
  value: string;
  onValueChange: (v: string) => void;
  options: { value: string; label: string }[];
  disabled?: boolean;
  /** Show an "All" (clear) option. False for filters that must always hold a
   *  value (e.g. Academic Year). */
  allowClear?: boolean;
}) {
  return (
    <div className="space-y-1.5">
      <span className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
        {label}
      </span>
      <Select value={value} onValueChange={onValueChange} disabled={disabled}>
        <SelectTrigger>
          <SelectValue placeholder="All" />
        </SelectTrigger>
        <SelectContent>
          {allowClear && <SelectItem value={ANY}>All</SelectItem>}
          {options.map((o) => (
            <SelectItem key={o.value} value={o.value}>
              {o.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );
}

function formatRefreshed(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' });
}
