'use client';

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { useSelectedSchool } from '@/lib/context/SelectedSchoolContext';

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
        value={schoolId ?? undefined}
        onValueChange={(v) => setSchoolId(v)}
      >
        <SelectTrigger className="w-full">
          <SelectValue placeholder="Select school" />
        </SelectTrigger>
        <SelectContent>
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
