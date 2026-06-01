'use client';

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { useSelectedSchool } from '@/lib/context/SelectedSchoolContext';

// Select cannot hold an empty-string value, so a sentinel stands in for the
// "use my primary school" (backend fallback) option.
const ANY = '__any__';

export default function SchoolSwitcher() {
  const { schoolId, setSchoolId, schools } = useSelectedSchool();

  // A single-school member has nothing to switch between.
  if (schools.length <= 1) return null;

  return (
    <div className="flex flex-col gap-1">
      <span className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
        School
      </span>
      <Select
        value={schoolId ?? ANY}
        onValueChange={(v) => setSchoolId(v === ANY ? null : v)}
      >
        <SelectTrigger className="w-full">
          <SelectValue placeholder="All schools" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value={ANY}>All schools</SelectItem>
          {schools.map((s) => (
            <SelectItem key={s.school_id} value={s.school_id}>
              {s.short_name || s.name}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );
}
