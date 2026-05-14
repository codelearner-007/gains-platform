'use client';

import { AlertCircle, RotateCcw } from 'lucide-react';
import { Button } from '@/components/ui/button';

interface ErrorStateProps {
  message?: string;
  onRetry?: () => void;
}

export default function ErrorState({
  message = 'Could not load report.',
  onRetry,
}: ErrorStateProps) {
  return (
    <div className="w-full flex justify-center">
      <div
        className="bg-card border border-border rounded-lg p-8 flex flex-col items-center text-center gap-4"
        style={{ maxWidth: 480 }}
      >
        <AlertCircle className="h-10 w-10 text-destructive" />
        <div className="space-y-1">
          <h2 className="text-lg font-semibold text-foreground">
            Something went wrong
          </h2>
          <p className="text-sm text-muted-foreground">{message}</p>
        </div>
        {onRetry && (
          <Button onClick={onRetry} variant="outline" size="sm">
            <RotateCcw className="mr-2 h-3.5 w-3.5" />
            Retry
          </Button>
        )}
      </div>
    </div>
  );
}
