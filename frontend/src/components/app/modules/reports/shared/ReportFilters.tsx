'use client';

import { useEffect, useRef, type ReactNode } from 'react';
import { useQuery } from '@tanstack/react-query';
import { RotateCcw, SlidersHorizontal } from 'lucide-react';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { Skeleton } from '@/components/ui/skeleton';
import { reportsApi, reportsKeys } from '@/lib/reports/api-client';
import { useSelectedSchool } from '@/lib/context/SelectedSchoolContext';
import type { AssessmentFilters, SectionRow } from '@/lib/reports/types';

const ANY = '__any__';

interface ReportFiltersProps {
  /** Active filters. `section` carries a comma-joined nid CSV (or a legacy name). */
  value: AssessmentFilters;
  onChange: (next: AssessmentFilters) => void;
  /**
   * Render the Section slicer. The school-wide Standard/Strand Summary pages
   * read the per-question overall cube, which has no section grain (section is
   * a class-roster construct), so they pass `false`.
   */
  showSection?: boolean;
  /**
   * Gated reports (Year To Date, Forward View) are built for one
   * session/subject/grade at a time: Session drops its "All sessions" item,
   * Session/Subject/Grade are marked required, and the header explains why.
   */
  requireScope?: boolean;
  /**
   * Latest session resolved on the page. Shown as the Session value when the
   * URL carries none, so a gated report always has a concrete session.
   */
  resolvedSession?: string;
  /** Extra grid cells appended after Section (e.g. the Forward View threshold). */
  extras?: ReactNode;
}

/** D3 label: "{name} · {instructors}", degrading to whichever part exists. */
function sectionLabel(row: SectionRow): string {
  const name = row.section_name?.trim();
  const inst = row.section_instructors?.trim();
  if (name && inst) return `${name} · ${inst}`;
  if (name) return name;
  if (inst) return inst;
  return row.section_nids[0] ?? '';
}

export default function ReportFilters({
  value,
  onChange,
  showSection = true,
  requireScope = false,
  resolvedSession,
  extras,
}: ReportFiltersProps) {
  const { schoolId } = useSelectedSchool();

  const effectiveSession = value.session ?? resolvedSession;
  const { subject, grade, category } = value;

  const sessionsQ = useQuery({
    queryKey: reportsKeys.sessions(schoolId ?? undefined),
    queryFn: () => reportsApi.sessions(schoolId ?? undefined),
  });
  const subjectsQ = useQuery({
    queryKey: reportsKeys.subjects(schoolId ?? undefined),
    queryFn: () => reportsApi.subjects(schoolId ?? undefined),
  });
  const gradesQ = useQuery({
    queryKey: reportsKeys.grades(schoolId ?? undefined),
    queryFn: () => reportsApi.grades(schoolId ?? undefined),
  });

  // Section is scope-dependent: only fetched once session + subject + grade are
  // all resolved, so the list reflects the sections that actually taught them.
  const sectionScope = { session: effectiveSession, subject, grade, category };
  const sectionEnabled =
    showSection && Boolean(effectiveSession && subject && grade);
  const sectionsQ = useQuery({
    queryKey: reportsKeys.sections(schoolId ?? undefined, sectionScope),
    queryFn: () => reportsApi.sections(schoolId ?? undefined, sectionScope),
    enabled: sectionEnabled,
  });

  const sessions = sessionsQ.data ?? [];
  const sections = sectionsQ.data ?? [];

  const subjectsUnique = uniqueValues(subjectsQ.data, (s) => s.subject);
  const categoriesUnique = uniqueValues(subjectsQ.data, (s) => s.assessment_type);
  const gradesUnique = uniqueValues(gradesQ.data, (g) => g.grade);

  // Self-heal: when the scope CHANGES, drop a section value that no longer maps
  // to any option. Gated to scope-change so a legacy `?section=<name>` deep link
  // survives the first settle (backend still honours the name arm); the ref
  // guard also prevents the clear from looping on the resulting re-render.
  const prevScopeRef = useRef<string | null>(null);
  const scopeKey = `${effectiveSession ?? ''}|${subject ?? ''}|${grade ?? ''}|${category ?? ''}`;
  useEffect(() => {
    if (!sectionEnabled || sectionsQ.isLoading || !sectionsQ.data) return;
    const prev = prevScopeRef.current;
    if (prev !== null && prev !== scopeKey && value.section) {
      const valid = sectionsQ.data.some(
        (r) => r.section_nids.join(',') === value.section,
      );
      if (!valid) onChange({ ...value, section: undefined });
    }
    prevScopeRef.current = scopeKey;
  }, [sectionEnabled, sectionsQ.isLoading, sectionsQ.data, scopeKey, value, onChange]);

  function update(field: keyof AssessmentFilters, raw: string) {
    const v = raw === ANY ? undefined : raw;
    onChange({ ...value, [field]: v });
  }

  const isDirty = Object.values(value).some((v) => Boolean(v));

  return (
    <section
      aria-label="Report filters"
      className="rounded-lg border border-border bg-card p-4 shadow-sm print:hidden"
    >
      <div className="mb-3 flex items-center justify-between gap-2">
        <div className="flex min-w-0 items-center gap-2">
          <SlidersHorizontal className="h-4 w-4 shrink-0 text-muted-foreground" />
          <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            Filters
          </span>
          {requireScope && (
            <span className="hidden truncate text-xs text-muted-foreground md:inline">
              Session, subject and grade shape this report
            </span>
          )}
        </div>
        <Button
          variant="ghost"
          size="sm"
          onClick={() => onChange({})}
          disabled={!isDirty}
          aria-label="Reset filters"
        >
          <RotateCcw className="h-4 w-4" />
          Reset
        </Button>
      </div>

      <div className="grid gap-3 [grid-template-columns:repeat(auto-fit,minmax(170px,1fr))]">
        <FilterField
          id="rf-session"
          label="Session"
          required={requireScope}
          loading={sessionsQ.isLoading}
        >
          <Select
            // Single-year semantics are driven by whether the page supplies a
            // `resolvedSession` (all 4 yearly reports do → default to the latest
            // year, no "All sessions" pooling). Reports that omit it (per-
            // assessment views) keep the "All sessions" option.
            value={
              resolvedSession != null
                ? (value.session ?? resolvedSession)
                : (value.session ?? ANY)
            }
            onValueChange={(v) => update('session', v)}
          >
            <SelectTrigger
              id="rf-session"
              className="w-full"
              aria-required={requireScope || undefined}
            >
              <SelectValue
                placeholder={
                  resolvedSession != null ? 'Select session' : 'All sessions'
                }
              />
            </SelectTrigger>
            <SelectContent>
              {resolvedSession == null && (
                <SelectItem value={ANY}>All sessions</SelectItem>
              )}
              {sessions.map((s) => (
                <SelectItem
                  key={s.session_id}
                  value={s.session ?? s.session_id}
                >
                  {s.session ?? s.session_id}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </FilterField>

        <FilterField
          id="rf-subject"
          label="Subject"
          required={requireScope}
          loading={subjectsQ.isLoading}
        >
          <Select
            value={
              requireScope ? (value.subject ?? '') : (value.subject ?? ANY)
            }
            onValueChange={(v) => update('subject', v)}
          >
            <SelectTrigger
              id="rf-subject"
              className="w-full"
              aria-required={requireScope || undefined}
            >
              <SelectValue
                placeholder={requireScope ? 'Select subject' : 'All subjects'}
              />
            </SelectTrigger>
            <SelectContent>
              {!requireScope && (
                <SelectItem value={ANY}>All subjects</SelectItem>
              )}
              {subjectsUnique.map((s) => (
                <SelectItem key={s} value={s}>
                  {s}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </FilterField>

        <FilterField
          id="rf-grade"
          label="Grade"
          required={requireScope}
          loading={gradesQ.isLoading}
        >
          <Select
            value={requireScope ? (value.grade ?? '') : (value.grade ?? ANY)}
            onValueChange={(v) => update('grade', v)}
          >
            <SelectTrigger
              id="rf-grade"
              className="w-full"
              aria-required={requireScope || undefined}
            >
              <SelectValue
                placeholder={requireScope ? 'Select grade' : 'All grades'}
              />
            </SelectTrigger>
            <SelectContent>
              {!requireScope && <SelectItem value={ANY}>All grades</SelectItem>}
              {gradesUnique.map((g) => (
                <SelectItem key={g} value={g}>
                  {g}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </FilterField>

        <FilterField
          id="rf-category"
          label="Category"
          loading={subjectsQ.isLoading}
        >
          <Select
            value={value.category ?? ANY}
            onValueChange={(v) => update('category', v)}
          >
            <SelectTrigger id="rf-category" className="w-full">
              <SelectValue placeholder="All categories" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={ANY}>All categories</SelectItem>
              {categoriesUnique.map((c) => (
                <SelectItem key={c} value={c}>
                  {c}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </FilterField>

        {showSection && (
          <FilterField
            id="rf-section"
            label="Section"
            loading={sectionEnabled && sectionsQ.isLoading}
          >
            <Select
              // While disabled (no subject+grade yet) show nothing so the
              // "Select subject & grade first" placeholder renders instead of
              // the selected "All sections" sentinel.
              value={sectionEnabled ? (value.section ?? ANY) : ''}
              onValueChange={(v) => update('section', v)}
              disabled={!sectionEnabled}
            >
              <SelectTrigger id="rf-section" className="w-full">
                <SelectValue
                  placeholder={
                    sectionEnabled
                      ? 'All sections'
                      : 'Select subject & grade first'
                  }
                />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={ANY}>All sections</SelectItem>
                {sections.map((row) => {
                  const key = row.section_nids.join(',');
                  return (
                    <SelectItem key={key} value={key}>
                      {sectionLabel(row)}
                    </SelectItem>
                  );
                })}
              </SelectContent>
            </Select>
          </FilterField>
        )}

        {extras}
      </div>
    </section>
  );
}

function FilterField({
  id,
  label,
  required = false,
  loading = false,
  children,
}: {
  id: string;
  label: string;
  required?: boolean;
  loading?: boolean;
  children: ReactNode;
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <Label htmlFor={id} className="text-xs font-medium text-muted-foreground">
        {label}
        {required && (
          <span className="text-destructive" aria-hidden>
            {' '}
            *
          </span>
        )}
      </Label>
      {loading ? <Skeleton className="h-9 w-full" /> : children}
    </div>
  );
}

/** Distinct non-empty values of `key(row)`, in first-seen order. */
function uniqueValues<T>(
  rows: readonly T[] | undefined,
  key: (row: T) => string | null | undefined,
): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const row of rows ?? []) {
    const v = key(row);
    if (v && !seen.has(v)) {
      seen.add(v);
      out.push(v);
    }
  }
  return out;
}
