'use client';

import { useEffect } from 'react';
import ErrorState from '@/components/app/modules/reports/shared/ErrorState';

export default function ReportsError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error('Reports error boundary:', error);
  }, [error]);

  return <ErrorState message={error.message} onRetry={reset} />;
}
