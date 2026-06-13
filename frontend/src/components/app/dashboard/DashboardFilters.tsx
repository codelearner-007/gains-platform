'use client';

import { Search, X } from 'lucide-react';
import type { AssessmentFilters } from '@/lib/reports/types';
import ReportFilters from '@/components/app/modules/reports/shared/ReportFilters';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';

interface DashboardFiltersProps {
  filters: AssessmentFilters;
  onFiltersChange: (next: AssessmentFilters) => void;
  search: string;
  onSearchChange: (next: string) => void;
}

/**
 * Dashboard filter card: a prominent assessment-name search on top, the
 * school-scoped scope slicers below (the shared ReportFilters in `bare` mode),
 * and a single Clear that resets both. The slicers drive every dashboard
 * section (KPIs + summary table); the search filters the active table client-side.
 */
export default function DashboardFilters({
  filters,
  onFiltersChange,
  search,
  onSearchChange,
}: DashboardFiltersProps) {
  const dirty = search.length > 0 || Object.keys(filters).length > 0;

  return (
    <div className="space-y-3 rounded-lg border border-border bg-card p-4">
      <div className="flex items-center gap-3">
        <div className="relative flex-1">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            type="search"
            value={search}
            onChange={(e) => onSearchChange(e.target.value)}
            placeholder="Search the table…"
            aria-label="Search the assessments summary"
            className="pl-9"
          />
        </div>
        <Button
          variant="ghost"
          size="sm"
          onClick={() => {
            onFiltersChange({});
            onSearchChange('');
          }}
          disabled={!dirty}
          className="shrink-0"
        >
          <X className="mr-1 h-3.5 w-3.5" />
          Clear
        </Button>
      </div>

      <ReportFilters value={filters} onChange={onFiltersChange} bare />
    </div>
  );
}
