import { X, Filter, Shield, Mail } from 'lucide-react';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import type { UserFilters as UserFiltersType, RoleResponse } from '@/lib/services/rbac.service';

interface UserFiltersProps {
  filters: UserFiltersType;
  searchQuery: string;
  roles: RoleResponse[];
  loadingRoles: boolean;
  activeFilters: [string, string | number | boolean][];
  hasActiveFilters: boolean;
  onFilterChange: (key: keyof UserFiltersType, value: string | boolean | undefined) => void;
  onRemoveFilter: (key: keyof UserFiltersType) => void;
  onClearAllFilters: () => void;
}

function getFilterDisplay(key: string, value: string | number | boolean): { displayKey: string; displayValue: string } {
  switch (key) {
    case 'email_verified':
      return { displayKey: 'Email', displayValue: value ? 'Verified' : 'Not Verified' };
    case 'role':
      return { displayKey: 'Role', displayValue: String(value) };
    case 'status':
      return { displayKey: 'Status', displayValue: value === 'active' ? 'Active' : 'Banned' };
    case 'search':
      return { displayKey: 'Search', displayValue: String(value) };
    default:
      return { displayKey: key, displayValue: String(value) };
  }
}

export function UserFiltersPanel({
  filters,
  searchQuery,
  roles,
  loadingRoles,
  activeFilters,
  hasActiveFilters,
  onFilterChange,
  onRemoveFilter,
  onClearAllFilters,
}: UserFiltersProps) {
  return (
    <Card className="border-border shadow-sm">
      <CardContent className="pt-6">
        <div className="space-y-5">
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
            {/* Search */}
            <div className="space-y-2">
              <Label className="text-sm font-medium">Search</Label>
              <Input
                placeholder="Search by email..."
                value={searchQuery}
                onChange={(e) => onFilterChange('search', e.target.value)}
                aria-label="Search users by email"
              />
            </div>

            {/* Role Filter */}
            <div className="space-y-2">
              <Label className="text-sm font-medium">Role</Label>
              <Select
                value={filters.role || 'all'}
                onValueChange={(value) => onFilterChange('role', value)}
                disabled={loadingRoles}
              >
                <SelectTrigger aria-label="Filter by role">
                  <div className="flex items-center gap-2">
                    <Shield className="h-4 w-4 text-muted-foreground" />
                    <SelectValue placeholder="All Roles" />
                  </div>
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All Roles</SelectItem>
                  {roles.map((role) => (
                    <SelectItem key={role.id} value={role.name}>
                      {role.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            {/* Status Filter */}
            <div className="space-y-2">
              <Label className="text-sm font-medium">Status</Label>
              <Select
                value={filters.status || 'all'}
                onValueChange={(value) => onFilterChange('status', value)}
              >
                <SelectTrigger aria-label="Filter by status">
                  <div className="flex items-center gap-2">
                    <Filter className="h-4 w-4 text-muted-foreground" />
                    <SelectValue placeholder="All Status" />
                  </div>
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All Status</SelectItem>
                  <SelectItem value="active">Active</SelectItem>
                  <SelectItem value="banned">Banned</SelectItem>
                </SelectContent>
              </Select>
            </div>

            {/* Email Verified Filter */}
            <div className="space-y-2">
              <Label className="text-sm font-medium">Email Verified</Label>
              <Select
                value={
                  filters.email_verified === undefined ? 'all' : String(filters.email_verified)
                }
                onValueChange={(value) =>
                  onFilterChange(
                    'email_verified',
                    value === 'all' ? undefined : value === 'true'
                  )
                }
              >
                <SelectTrigger aria-label="Filter by email verification status">
                  <div className="flex items-center gap-2">
                    <Mail className="h-4 w-4 text-muted-foreground" />
                    <SelectValue placeholder="All" />
                  </div>
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All</SelectItem>
                  <SelectItem value="true">Verified</SelectItem>
                  <SelectItem value="false">Not Verified</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>

          {/* Active Filters */}
          {hasActiveFilters && (
            <div className="flex items-center gap-3 pt-2 border-t border-border">
              <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                Active Filters:
              </span>
              <div className="flex items-center gap-2 flex-wrap">
                {activeFilters.map(([key, value]) => {
                  const { displayKey, displayValue } = getFilterDisplay(key, value);
                  return (
                    <Badge
                      key={key}
                      variant="secondary"
                      className="gap-2 pl-3 pr-2 py-1.5 bg-primary/10 text-primary border-primary/20 hover:bg-primary/20"
                    >
                      <span className="text-xs font-medium">
                        {displayKey}: {displayValue}
                      </span>
                      <Button
                        variant="ghost"
                        size="icon"
                        onClick={() => onRemoveFilter(key as keyof UserFiltersType)}
                        className="h-5 w-5 hover:bg-primary/20 rounded-full p-0.5 transition-colors"
                        aria-label={`Remove ${displayKey} filter`}
                      >
                        <X className="h-3 w-3" />
                      </Button>
                    </Badge>
                  );
                })}
                <div className="flex items-center gap-2">
                  <span className="text-muted-foreground">|</span>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={onClearAllFilters}
                    className="h-7 px-2 text-xs font-medium hover:bg-destructive/10 hover:text-destructive"
                  >
                    Clear All
                  </Button>
                </div>
              </div>
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
