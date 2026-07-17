'use client';

import { useState } from 'react';
import { Ban, CheckCircle2, Trash2, MailCheck, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import type { BulkUserAction } from '@/lib/services/users.service';

interface BulkActionBarProps {
  count: number;
  loading: boolean;
  canUpdate: boolean;
  canDelete: boolean;
  onAction: (action: BulkUserAction) => void;
  onClear: () => void;
}

interface Confirm {
  action: BulkUserAction;
  title: string;
  body: string;
  destructive: boolean;
  requireCount: boolean;
}

export function BulkActionBar({
  count,
  loading,
  canUpdate,
  canDelete,
  onAction,
  onClear,
}: BulkActionBarProps) {
  const [confirm, setConfirm] = useState<Confirm | null>(null);
  const [typed, setTyped] = useState('');

  if (count === 0) return null;

  const ask = (c: Confirm) => {
    setTyped('');
    setConfirm(c);
  };

  const run = () => {
    if (!confirm) return;
    onAction(confirm.action);
    setConfirm(null);
  };

  const confirmDisabled =
    loading || (confirm?.requireCount === true && typed.trim() !== String(count));

  return (
    <>
      <div className="fixed inset-x-0 bottom-6 z-40 flex justify-center px-4 pointer-events-none">
        <div className="pointer-events-auto flex items-center gap-2 rounded-full border border-border bg-card px-3 py-2 shadow-lg">
          <span className="px-2 text-sm font-medium tabular-nums">
            {count} selected
          </span>
          <span className="h-5 w-px bg-border" aria-hidden />

          {canUpdate && (
            <>
              <Button
                variant="ghost"
                size="sm"
                disabled={loading}
                onClick={() =>
                  ask({
                    action: 'resend-invite',
                    title: `Resend invitations to ${count} user${count === 1 ? '' : 's'}?`,
                    body: 'Each selected user gets a fresh invitation email. Already-active users are skipped.',
                    destructive: false,
                    requireCount: false,
                  })
                }
              >
                <MailCheck className="h-4 w-4 mr-1.5" />
                Resend
              </Button>
              <Button
                variant="ghost"
                size="sm"
                disabled={loading}
                onClick={() =>
                  ask({
                    action: 'unban',
                    title: `Unban ${count} user${count === 1 ? '' : 's'}?`,
                    body: 'The selected users will be able to sign in again.',
                    destructive: false,
                    requireCount: false,
                  })
                }
              >
                <CheckCircle2 className="h-4 w-4 mr-1.5" />
                Unban
              </Button>
              <Button
                variant="ghost"
                size="sm"
                disabled={loading}
                onClick={() =>
                  ask({
                    action: 'ban',
                    title: `Ban ${count} user${count === 1 ? '' : 's'}?`,
                    body: 'Banned users are signed out immediately and cannot log in until unbanned. Superadmins in the selection are skipped.',
                    destructive: true,
                    requireCount: false,
                  })
                }
              >
                <Ban className="h-4 w-4 mr-1.5" />
                Ban
              </Button>
            </>
          )}

          {canDelete && (
            <Button
              variant="ghost"
              size="sm"
              className="text-destructive hover:text-destructive hover:bg-destructive/10"
              disabled={loading}
              onClick={() =>
                ask({
                  action: 'delete',
                  title: `Delete ${count} user${count === 1 ? '' : 's'}?`,
                  body: 'This permanently deletes the selected accounts. This cannot be undone. Superadmins in the selection are skipped.',
                  destructive: true,
                  requireCount: true,
                })
              }
            >
              <Trash2 className="h-4 w-4 mr-1.5" />
              Delete
            </Button>
          )}

          <span className="h-5 w-px bg-border" aria-hidden />
          <Button
            variant="ghost"
            size="icon"
            className="h-8 w-8"
            onClick={onClear}
            aria-label="Clear selection"
          >
            <X className="h-4 w-4" />
          </Button>
        </div>
      </div>

      <Dialog open={!!confirm} onOpenChange={(o) => !o && setConfirm(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{confirm?.title}</DialogTitle>
            <DialogDescription>{confirm?.body}</DialogDescription>
          </DialogHeader>
          {confirm?.requireCount && (
            <div className="space-y-2">
              <label className="text-sm text-muted-foreground">
                Type <span className="font-semibold text-foreground">{count}</span>{' '}
                to confirm.
              </label>
              <Input
                value={typed}
                onChange={(e) => setTyped(e.target.value)}
                inputMode="numeric"
                placeholder={String(count)}
                aria-label="Confirmation count"
              />
            </div>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => setConfirm(null)}>
              Cancel
            </Button>
            <Button
              variant={confirm?.destructive ? 'destructive' : 'default'}
              disabled={confirmDisabled}
              onClick={run}
            >
              {loading ? 'Working…' : 'Confirm'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
