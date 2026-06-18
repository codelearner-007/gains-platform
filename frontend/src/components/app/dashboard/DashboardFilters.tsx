'use client';

import type { AssessmentFilters } from '@/lib/reports/types';
import SearchInput from './SearchInput';
import FilterPopover from './FilterPopover';

interface DashboardFiltersProps {
  filters: AssessmentFilters;
  onFiltersChange: (next: AssessmentFilters) => void;
  search: string;
  onSearchChange: (next: string) => void;
  searchLoading?: boolean;
  resultCount?: number;
  refreshedAt?: string | null;
  onRefresh: () => void;
  refreshing?: boolean;
  /** Lock the popover filter controls while filter-dependent data refetches.
   *  The search box stays enabled (it is debounced + independently safe). */
  filtersDisabled?: boolean;
}

/**
 * Slim dashboard controls bar: a compact assessment-name search (left) and the
 * on-demand secondary-filter popover (right, holding Academic Year / Assessment
 * Type / Section Instructors + Refresh Dataset). Subject + grade live up front
 * as cards / chips, so they are intentionally not here.
 */
export default function DashboardFilters({
  filters,
  onFiltersChange,
  search,
  onSearchChange,
  searchLoading,
  resultCount,
  refreshedAt,
  onRefresh,
  refreshing,
  filtersDisabled,
}: DashboardFiltersProps) {
  return (
    <div className="flex items-center justify-between gap-3">
      <SearchInput
        value={search}
        onChange={onSearchChange}
        loading={searchLoading}
        resultCount={resultCount}
      />
      <FilterPopover
        filters={filters}
        onChange={onFiltersChange}
        refreshedAt={refreshedAt}
        onRefresh={onRefresh}
        refreshing={refreshing}
        disabled={filtersDisabled}
      />
    </div>
  );
}
