'use client';

import { useState, useMemo } from 'react';
import { Search } from 'lucide-react';
import { Input } from '@/components/ui/input';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { useSchoolsManagement } from './useSchoolsManagement';
import { SchoolCardGrid } from './SchoolCardGrid';
import { SchoolCreateDialog } from './SchoolCreateDialog';
import { SchoolEditDialog } from './SchoolEditDialog';
import { SchoolLTIDialog } from './SchoolLTIDialog';

type StatusFilter = 'all' | 'active' | 'inactive';

export default function AdminSchoolsPage() {
  const {
    schools,
    total,
    loading,
    error,
    canCreate,
    canUpdate,
    canManageLti,
    createOpen,
    setCreateOpen,
    editSchool,
    setEditSchool,
    ltiSchool,
    setLtiSchool,
    reload,
  } = useSchoolsManagement();

  const [search, setSearch] = useState('');
  const [status, setStatus] = useState<StatusFilter>('all');

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return schools.filter((s) => {
      if (status === 'active' && !s.is_active) return false;
      if (status === 'inactive' && s.is_active) return false;
      if (!q) return true;
      return (
        s.name.toLowerCase().includes(q) ||
        s.short_name.toLowerCase().includes(q)
      );
    });
  }, [schools, search, status]);

  const hasFilters = search.trim() !== '' || status !== 'all';

  return (
    <div className="space-y-6 max-w-[1600px]">
      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-foreground">Schools</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Manage schools (tenants)
            {!loading && (
              <span className="ml-1">
                · {total} {total === 1 ? 'school' : 'schools'}
              </span>
            )}
          </p>
        </div>
        {canCreate && (
          <SchoolCreateDialog
            open={createOpen}
            onOpenChange={setCreateOpen}
            onSuccess={reload}
          />
        )}
      </div>

      {/* Toolbar */}
      <div className="flex flex-wrap items-center gap-2">
        <div className="relative min-w-[220px] flex-1 sm:max-w-sm">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            className="pl-9"
            placeholder="Search schools…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            aria-label="Search schools"
          />
        </div>
        <Select value={status} onValueChange={(v) => setStatus(v as StatusFilter)}>
          <SelectTrigger className="w-[150px]" aria-label="Filter by status">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All status</SelectItem>
            <SelectItem value="active">Active</SelectItem>
            <SelectItem value="inactive">Inactive</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {/* Card grid */}
      <SchoolCardGrid
        schools={filtered}
        loading={loading}
        error={error}
        canUpdate={canUpdate}
        canManageLti={canManageLti}
        hasFilters={hasFilters}
        onEdit={setEditSchool}
        onManageLti={setLtiSchool}
      />

      {/* Edit Dialog */}
      <SchoolEditDialog
        school={editSchool}
        onClose={() => setEditSchool(null)}
        onSuccess={reload}
      />

      {/* LTI Configuration Dialog */}
      <SchoolLTIDialog
        school={ltiSchool}
        onClose={() => setLtiSchool(null)}
      />
    </div>
  );
}
