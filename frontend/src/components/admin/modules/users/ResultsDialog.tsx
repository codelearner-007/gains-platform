'use client';

import { Check, XCircle } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';

export interface ResultItem {
  label: string;
  ok: boolean;
  error?: string;
}

interface ResultsDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  results: ResultItem[];
}

export function ResultsDialog({
  open,
  onOpenChange,
  title,
  results,
}: ResultsDialogProps) {
  const ok = results.filter((r) => r.ok).length;
  const failed = results.length - ok;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
        </DialogHeader>

        <div className="flex gap-2 text-sm">
          <Badge className="bg-success/15 text-success border-success/30">
            {ok} succeeded
          </Badge>
          {failed > 0 && (
            <Badge className="bg-destructive/10 text-destructive border-destructive/30">
              {failed} failed
            </Badge>
          )}
        </div>

        <div className="max-h-72 space-y-1.5 overflow-y-auto">
          {results.map((r, i) => (
            <div
              key={`${r.label}-${i}`}
              className="flex items-center justify-between gap-3 rounded-md border border-border px-3 py-2 text-sm"
            >
              <span className="truncate">{r.label}</span>
              {r.ok ? (
                <span className="flex items-center gap-1 whitespace-nowrap text-success">
                  <Check className="h-3.5 w-3.5" /> Done
                </span>
              ) : (
                <span
                  className="flex items-center gap-1 whitespace-nowrap text-destructive"
                  title={r.error}
                >
                  <XCircle className="h-3.5 w-3.5" />
                  {r.error ?? 'Failed'}
                </span>
              )}
            </div>
          ))}
        </div>

        <DialogFooter>
          <Button onClick={() => onOpenChange(false)}>Close</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
