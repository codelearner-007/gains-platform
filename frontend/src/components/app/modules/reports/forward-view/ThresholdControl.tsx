'use client';

import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Label } from '@/components/ui/label';

/** Preset flag cutoffs, as percent integers (URL `?threshold=<pct-int>`). */
const THRESHOLD_PRESETS = [50, 55, 60, 65, 70, 75, 80, 85] as const;

const HELPER = 'Standards scoring below this are flagged.';

interface ThresholdControlProps {
  /** Current cutoff as a percent integer (e.g. 70). */
  value: number;
}

/**
 * "Flag below" cutoff control, shaped as a single labeled cell so it drops
 * straight into the shared filter grid via ReportFilters' `extras` slot. Writes
 * `?threshold=<pct-int>` via `router.replace`, MERGING the current search params
 * so the active filters (and school scope) survive. The percent→fraction
 * conversion happens at the api-client boundary in the page, not here.
 */
export default function ThresholdControl({ value }: ThresholdControlProps) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  function handleChange(next: string) {
    const params = new URLSearchParams(searchParams.toString());
    params.set('threshold', next);
    router.replace(`${pathname}?${params.toString()}`);
  }

  return (
    <div className="flex flex-col gap-1.5">
      <Label
        htmlFor="fv-threshold"
        className="text-xs font-medium text-muted-foreground"
      >
        Flag below
      </Label>
      <Select value={String(value)} onValueChange={handleChange}>
        <SelectTrigger id="fv-threshold" className="w-full" title={HELPER}>
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {THRESHOLD_PRESETS.map((p) => (
            <SelectItem key={p} value={String(p)}>
              {p}%
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );
}
