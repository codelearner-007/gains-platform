'use client';

import { useState, useEffect, type ReactNode } from 'react';
import {
  AlertDialog,
  AlertDialogContent,
  AlertDialogHeader,
  AlertDialogFooter,
  AlertDialogTitle,
  AlertDialogDescription,
  AlertDialogCancel,
} from '@/components/ui/alert-dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';

interface ConfirmActionDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description: ReactNode;
  confirmLabel: string;
  variant?: 'default' | 'destructive';
  /** If set, the user must type this exact value to enable the confirm button. */
  typedChallenge?: string;
  challengeHint?: ReactNode;
  loading?: boolean;
  onConfirm: () => void;
}

/**
 * Reusable confirmation dialog for admin actions. Every user-management action —
 * individual and bulk — is routed through this so nothing fires on a single
 * click. Destructive actions may require a typed challenge (an email, a count).
 */
export function ConfirmActionDialog({
  open,
  onOpenChange,
  title,
  description,
  confirmLabel,
  variant = 'default',
  typedChallenge,
  challengeHint,
  loading = false,
  onConfirm,
}: ConfirmActionDialogProps) {
  const [typed, setTyped] = useState('');

  useEffect(() => {
    if (open) setTyped('');
  }, [open]);

  const challengeOk = !typedChallenge || typed.trim() === typedChallenge;

  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{title}</AlertDialogTitle>
          <AlertDialogDescription asChild>
            <div className="text-sm text-muted-foreground">{description}</div>
          </AlertDialogDescription>
        </AlertDialogHeader>

        {typedChallenge && (
          <div className="space-y-2">
            <Label className="text-sm text-muted-foreground">
              {challengeHint ?? (
                <>
                  Type <span className="font-semibold text-foreground">{typedChallenge}</span> to
                  confirm.
                </>
              )}
            </Label>
            <Input
              value={typed}
              onChange={(e) => setTyped(e.target.value)}
              placeholder={typedChallenge}
              autoComplete="off"
              aria-label="Confirmation input"
            />
          </div>
        )}

        <AlertDialogFooter>
          <AlertDialogCancel disabled={loading}>Cancel</AlertDialogCancel>
          <Button
            variant={variant}
            disabled={loading || !challengeOk}
            onClick={onConfirm}
          >
            {loading ? 'Working…' : confirmLabel}
          </Button>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
