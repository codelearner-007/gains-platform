'use client';

import type { ReactNode } from 'react';
import LoadingState from './LoadingState';
import ErrorState from './ErrorState';

interface AssessmentReportShellProps<T> {
  /** URL params present? When false, render nothing (the hook redirects). */
  ready: boolean;
  isLoading: boolean;
  isError: boolean;
  error: unknown;
  data: T | undefined;
  loadingLabel: string;
  onRetry: () => void;
  /** Rendered only once `data` is present (and any params are ready). */
  children: (data: T) => ReactNode;
}

/**
 * Renders the loading / error / not-ready guards shared by every assessment
 * report page, then hands off to `children(data)` once the payload is loaded.
 * Mirrors the verbatim guard ladder the pages used to inline:
 *   !ready → null · isLoading → LoadingState · isError → ErrorState · !data → null
 */
export default function AssessmentReportShell<T>({
  ready,
  isLoading,
  isError,
  error,
  data,
  loadingLabel,
  onRetry,
  children,
}: AssessmentReportShellProps<T>) {
  if (!ready) return null;
  if (isLoading) return <LoadingState label={loadingLabel} />;
  if (isError)
    return (
      <ErrorState
        message={error instanceof Error ? error.message : 'Could not load report.'}
        onRetry={onRetry}
      />
    );
  if (!data) return null;
  return <>{children(data)}</>;
}
