'use client';

import { X, Filter, Search } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import type {
  UserFilters as UserFiltersType,
  RoleResponse,
} from '@/lib/services/rbac.service';
import type { School } from '@/lib/services/schools.service';

interface UserFiltersProps {
  filters: UserFiltersType;
  searchQuery: string;
  roles: RoleResponse[];
  schools: School[];
  loadingRoles: boolean;
  activeFilters: [string, string | number | boolean][];
  hasActiveFilters: boolean;
  onFilterChange: (
    key: keyof UserFiltersType,
    value: string | number | boolean | undefined,
  ) => void;
  onRemoveFilter: (key: keyof UserFiltersType) => void;
  onClearAllFilters: () => void;
}

const PAGE_SIZES = [20, 50, 100];

function filterChip(
  key: string,
  value: string | number | boolean,
  schools: School[],
): { label: string; value: string } {
  switch (key) {
    case 'email_verified':
      return { label: 'Email', value: value ? 'Verified' : 'Not verified' };
    case 'role':
      return { label: 'Role', value: String(value) };
    case 'status':
      return { label: 'Status', value: value === 'active' ? 'Active' : 'Banned' };
    case 'search':
      return { label: 'Search', value: String(value) };
    case 'school_id': {
      const s = schools.find((x) => x.school_id === value);
      return { label: 'School', value: s ? s.name : String(value) };
    }
    default:
      return { label: key, value: String(value) };
  }
}

export function UserFiltersPanel({
  filters,
  searchQuery,
  roles,
  schools,
  loadingRoles,
  activeFilters,
  hasActiveFilters,
  onFilterChange,
  onRemoveFilter,
  onClearAllFilters,
}: UserFiltersProps) {
  const menuCount = activeFilters.filter(([k]) => k !== 'search').length;
  const activeSchools = schools.filter((s) => s.is_active);

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        {/* Search — always visible */}
        <div className="relative min-w-[220px] flex-1 sm:max-w-sm">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            className="pl-9"
            placeholder="Search by email…"
            value={searchQuery}
            onChange={(e) => onFilterChange('search', e.target.value)}
            aria-label="Search users by email"
          />
        </div>

        {/* Filters — in a menu */}
        <Popover>
          <PopoverTrigger asChild>
            <Button variant="outline" className="gap-2">
              <Filter className="h-4 w-4" />
              Filters
              {menuCount > 0 && (
                <Badge className="ml-1 h-5 min-w-5 justify-center rounded-full bg-primary px-1.5 text-primary-foreground tabular-nums">
                  {menuCount}
                </Badge>
              )}
            </Button>
          </PopoverTrigger>
          <PopoverContent align="end" className="w-72 space-y-4">
            <div className="space-y-1.5">
              <Label className="text-xs font-medium">Role</Label>
              <Select
                value={filters.role || 'all'}
                onValueChange={(v) => onFilterChange('role', v)}
                disabled={loadingRoles}
              >
                <SelectTrigger aria-label="Filter by role">
                  <SelectValue placeholder="All roles" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All roles</SelectItem>
                  {roles.map((role) => (
                    <SelectItem key={role.id} value={role.name}>
                      {role.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-1.5">
              <Label className="text-xs font-medium">School</Label>
              <Select
                value={filters.school_id || 'all'}
                onValueChange={(v) => onFilterChange('school_id', v)}
              >
                <SelectTrigger aria-label="Filter by school">
                  <SelectValue placeholder="All schools" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All schools</SelectItem>
                  {activeSchools.map((s) => (
                    <SelectItem key={s.school_id} value={s.school_id}>
                      {s.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-1.5">
              <Label className="text-xs font-medium">Status</Label>
              <Select
                value={filters.status || 'all'}
                onValueChange={(v) => onFilterChange('status', v)}
              >
                <SelectTrigger aria-label="Filter by status">
                  <SelectValue placeholder="All status" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All status</SelectItem>
                  <SelectItem value="active">Active</SelectItem>
                  <SelectItem value="banned">Banned</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-1.5">
              <Label className="text-xs font-medium">Email verified</Label>
              <Select
                value={
                  filters.email_verified === undefined
                    ? 'all'
                    : String(filters.email_verified)
                }
                onValueChange={(v) =>
                  onFilterChange(
                    'email_verified',
                    v === 'all' ? undefined : v === 'true',
                  )
                }
              >
                <SelectTrigger aria-label="Filter by email verification status">
                  <SelectValue placeholder="All" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All</SelectItem>
                  <SelectItem value="true">Verified</SelectItem>
                  <SelectItem value="false">Not verified</SelectItem>
                </SelectContent>
              </Select>
            </div>

            {menuCount > 0 && (
              <Button
                variant="ghost"
                size="sm"
                className="w-full text-muted-foreground"
                onClick={onClearAllFilters}
              >
                Clear all filters
              </Button>
            )}
          </PopoverContent>
        </Popover>

        {/* Page size */}
        <Select
          value={String(filters.page_size)}
          onValueChange={(v) => onFilterChange('page_size', Number(v))}
        >
          <SelectTrigger className="w-[130px]" aria-label="Rows per page">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {PAGE_SIZES.map((n) => (
              <SelectItem key={n} value={String(n)}>
                {n} / page
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {/* Active filter chips */}
      {hasActiveFilters && (
        <div className="flex flex-wrap items-center gap-2">
          {activeFilters.map(([key, value]) => {
            const chip = filterChip(key, value, schools);
            return (
              <Badge
                key={key}
                variant="secondary"
                className="gap-1.5 border-primary/20 bg-primary/10 py-1 pl-3 pr-1.5 text-primary"
              >
                <span className="text-xs font-medium">
                  {chip.label}: {chip.value}
                </span>
                <button
                  type="button"
                  onClick={() => onRemoveFilter(key as keyof UserFiltersType)}
                  className="rounded-full p-0.5 transition-colors hover:bg-primary/20"
                  aria-label={`Remove ${chip.label} filter`}
                >
                  <X className="h-3 w-3" />
                </button>
              </Badge>
            );
          })}
          <Button
            variant="ghost"
            size="sm"
            onClick={onClearAllFilters}
            className="h-7 px-2 text-xs text-muted-foreground hover:text-destructive"
          >
            Clear all
          </Button>
        </div>
      )}
    </div>
  );
}
