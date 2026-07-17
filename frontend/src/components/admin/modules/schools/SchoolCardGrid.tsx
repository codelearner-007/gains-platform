'use client';

import { Pencil, Clock, CalendarDays } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import type { School } from '@/lib/services/schools.service';

interface SchoolCardGridProps {
  schools: School[];
  loading: boolean;
  error: string | null;
  canUpdate: boolean;
  hasFilters: boolean;
  onEdit: (school: School) => void;
}

function initials(name: string): string {
  return name
    .split(/\s+/)
    .slice(0, 2)
    .map((w) => w[0])
    .join('')
    .toUpperCase();
}

function SchoolLogo({ school }: { school: School }) {
  if (school.logo_url) {
    // eslint-disable-next-line @next/next/no-img-element
    return (
      <img
        src={school.logo_url}
        alt=""
        className="h-14 w-14 shrink-0 rounded-lg border border-border object-contain bg-card"
      />
    );
  }
  return (
    <div className="flex h-14 w-14 shrink-0 items-center justify-center rounded-lg bg-muted text-base font-semibold text-muted-foreground">
      {initials(school.name)}
    </div>
  );
}

export function SchoolCardGrid({
  schools,
  loading,
  error,
  canUpdate,
  hasFilters,
  onEdit,
}: SchoolCardGridProps) {
  if (loading) {
    return (
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {Array.from({ length: 6 }).map((_, i) => (
          <div key={i} className="h-40 rounded-xl bg-muted animate-pulse" />
        ))}
      </div>
    );
  }
  if (error) {
    return (
      <div className="rounded-xl border border-destructive/40 bg-destructive/5 p-4 text-sm text-destructive">
        {error}
      </div>
    );
  }
  if (schools.length === 0) {
    return (
      <div className="rounded-xl border border-border bg-card p-12 text-center">
        <p className="text-sm font-medium text-muted-foreground">No schools found</p>
        <p className="text-xs text-muted-foreground mt-1">
          {hasFilters ? 'Try adjusting your search or filter.' : 'Create your first school to get started.'}
        </p>
      </div>
    );
  }

  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {schools.map((school) => (
        <div
          key={school.school_id}
          className="group flex flex-col rounded-xl border border-border bg-card p-5 card-hover"
        >
          <div className="flex items-start gap-4">
            <SchoolLogo school={school} />
            <div className="min-w-0 flex-1">
              <div className="flex items-start justify-between gap-2">
                <h3 className="truncate text-sm font-semibold text-foreground">
                  {school.name}
                </h3>
                <Badge
                  className={
                    school.is_active
                      ? 'bg-success/15 text-success border-success/30'
                      : 'bg-muted text-muted-foreground'
                  }
                >
                  {school.is_active ? 'Active' : 'Inactive'}
                </Badge>
              </div>
              <p className="truncate text-xs text-muted-foreground">
                {school.short_name}
              </p>
            </div>
          </div>

          <dl className="mt-4 space-y-1.5 text-xs text-muted-foreground">
            <div className="flex items-center gap-2">
              <CalendarDays className="h-3.5 w-3.5" />
              <span>Session: {school.current_session || '—'}</span>
            </div>
            <div className="flex items-center gap-2">
              <Clock className="h-3.5 w-3.5" />
              <span>{school.timezone}</span>
            </div>
          </dl>

          {canUpdate && (
            <div className="mt-4 pt-4 border-t border-border">
              <Button
                variant="outline"
                size="sm"
                className="w-full"
                onClick={() => onEdit(school)}
              >
                <Pencil className="h-3.5 w-3.5 mr-2" />
                Manage
              </Button>
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
