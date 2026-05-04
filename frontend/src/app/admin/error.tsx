'use client';

import { useEffect } from 'react';
import { Button } from '@/components/ui/button';
import { AlertCircle } from 'lucide-react';

export default function AdminError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error('Admin error boundary caught:', error);
  }, [error]);

  return (
    <div className="flex flex-col items-center justify-center min-h-[50vh] gap-4">
      <div className="flex items-center justify-center w-12 h-12 rounded-full bg-destructive/10">
        <AlertCircle className="h-6 w-6 text-destructive" />
      </div>
      <h2 className="text-xl font-semibold text-foreground">Something went wrong</h2>
      <p className="text-muted-foreground text-center max-w-md">
        An error occurred while loading this page. Please try again or contact support if the problem persists.
      </p>
      {error.message && (
        <div className="text-sm text-muted-foreground bg-muted p-3 rounded-lg border border-border max-w-md w-full">
          <p className="font-medium mb-1">Error details:</p>
          <p>{error.message}</p>
        </div>
      )}
      <Button onClick={reset} variant="outline">
        Try again
      </Button>
    </div>
  );
}
