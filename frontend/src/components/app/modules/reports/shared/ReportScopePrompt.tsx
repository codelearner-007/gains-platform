import { SlidersHorizontal } from 'lucide-react';

interface ReportScopePromptProps {
  /** Resolved session, folded into the body copy when present. */
  session?: string;
}

/**
 * Shared empty-state for the gated program reports (Year To Date, Forward
 * View). Those reports are built for one subject and grade at a time, so before
 * a scope is chosen we render this prompt in place of the report body — the
 * chrome (filter bar, breadcrumb, export) stays visible above it — pointing the
 * user at the filters rather than showing a blank canvas.
 */
export default function ReportScopePrompt({ session }: ReportScopePromptProps) {
  return (
    <div className="flex w-full justify-center py-6">
      <div className="flex max-w-md flex-col items-center gap-4 rounded-lg border border-dashed border-border bg-card p-8 text-center">
        <span className="flex h-12 w-12 items-center justify-center rounded-full bg-muted">
          <SlidersHorizontal
            className="h-6 w-6 text-muted-foreground"
            aria-hidden="true"
          />
        </span>
        <div className="space-y-1.5">
          <h2 className="text-base font-semibold text-foreground">
            Choose a subject and grade
          </h2>
          <p className="text-sm text-muted-foreground">
            This report is built for one subject and grade at a time
            {session ? ` for ${session}` : ''}. Pick them in the filters above.
          </p>
        </div>
      </div>
    </div>
  );
}
