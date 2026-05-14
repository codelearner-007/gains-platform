'use client';

import { useQuery } from '@tanstack/react-query';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Button } from '@/components/ui/button';
import { reportsApi, reportsKeys } from '@/lib/services/reports-service';
import type { AssessmentFilters } from '@/lib/reports/types';

const ANY = '__any__';

interface ReportFiltersProps {
  value: AssessmentFilters;
  onChange: (next: AssessmentFilters) => void;
}

export default function ReportFilters({ value, onChange }: ReportFiltersProps) {
  const sessionsQ = useQuery({
    queryKey: reportsKeys.sessions(),
    queryFn: () => reportsApi.sessions(),
  });
  const subjectsQ = useQuery({
    queryKey: reportsKeys.subjects(),
    queryFn: () => reportsApi.subjects(),
  });
  const gradesQ = useQuery({
    queryKey: reportsKeys.grades(),
    queryFn: () => reportsApi.grades(),
  });
  const sectionsQ = useQuery({
    queryKey: reportsKeys.sections(),
    queryFn: () => reportsApi.sections(),
  });

  function update(field: keyof AssessmentFilters, raw: string) {
    const v = raw === ANY ? undefined : raw;
    onChange({ ...value, [field]: v });
  }

  const sessions = sessionsQ.data ?? [];
  const subjects = subjectsQ.data ?? [];
  const grades = gradesQ.data ?? [];
  const sections = sectionsQ.data ?? [];

  const subjectsUnique = Array.from(
    new Map(
      subjects
        .filter((s) => s.subject)
        .map((s) => [s.subject as string, s.subject as string]),
    ).keys(),
  );
  const categoriesUnique = Array.from(
    new Map(
      subjects
        .filter((s) => s.assessment_type)
        .map((s) => [s.assessment_type as string, s.assessment_type as string]),
    ).keys(),
  );
  const gradesUnique = Array.from(
    new Map(
      grades
        .filter((g) => g.grade)
        .map((g) => [g.grade as string, g.grade as string]),
    ).keys(),
  );

  return (
    <div className="flex flex-wrap items-end gap-3 p-4 bg-card border border-border rounded-lg">
      <FilterField label="Session">
        <Select
          value={value.session ?? ANY}
          onValueChange={(v) => update('session', v)}
        >
          <SelectTrigger className="w-40">
            <SelectValue placeholder="Any" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ANY}>Any</SelectItem>
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

      <FilterField label="Category">
        <Select
          value={value.category ?? ANY}
          onValueChange={(v) => update('category', v)}
        >
          <SelectTrigger className="w-52">
            <SelectValue placeholder="Any" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ANY}>Any</SelectItem>
            {categoriesUnique.map((c) => (
              <SelectItem key={c} value={c}>
                {c}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </FilterField>

      <FilterField label="Subject">
        <Select
          value={value.subject ?? ANY}
          onValueChange={(v) => update('subject', v)}
        >
          <SelectTrigger className="w-44">
            <SelectValue placeholder="Any" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ANY}>Any</SelectItem>
            {subjectsUnique.map((s) => (
              <SelectItem key={s} value={s}>
                {s}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </FilterField>

      <FilterField label="Grade">
        <Select
          value={value.grade ?? ANY}
          onValueChange={(v) => update('grade', v)}
        >
          <SelectTrigger className="w-36">
            <SelectValue placeholder="Any" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ANY}>Any</SelectItem>
            {gradesUnique.map((g) => (
              <SelectItem key={g} value={g}>
                {g}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </FilterField>

      <FilterField label="Section">
        <Select
          value={value.section ?? ANY}
          onValueChange={(v) => update('section', v)}
        >
          <SelectTrigger className="w-44">
            <SelectValue placeholder="Any" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ANY}>Any</SelectItem>
            {sections.map((s) => {
              const label =
                s.section_name ?? s.section_code ?? s.section_nid;
              return (
                <SelectItem key={s.section_nid} value={label}>
                  {label}
                </SelectItem>
              );
            })}
          </SelectContent>
        </Select>
      </FilterField>

      <Button
        variant="ghost"
        size="sm"
        onClick={() => onChange({})}
        disabled={Object.keys(value).length === 0}
      >
        Clear
      </Button>
    </div>
  );
}

function FilterField({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex flex-col gap-1">
      <span className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
        {label}
      </span>
      {children}
    </div>
  );
}
