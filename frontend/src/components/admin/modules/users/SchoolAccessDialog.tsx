'use client';

import { useState, useEffect, useCallback } from 'react';
import { toast } from 'sonner';
import { Loader2, Star, Trash2, Plus } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { ConfirmActionDialog } from '@/components/admin/ConfirmActionDialog';
import type { UserWithRoles } from '@/lib/services/rbac.service';
import type { School } from '@/lib/services/schools.service';
import {
  listUserSchools,
  grantUserSchool,
  revokeUserSchool,
  type UserSchoolMembership,
} from '@/lib/services/users.service';

interface SchoolAccessDialogProps {
  user: UserWithRoles | null;
  schools: School[];
  loadingSchools: boolean;
  onOpenChange: (open: boolean) => void;
}

export function SchoolAccessDialog({
  user,
  schools,
  loadingSchools,
  onOpenChange,
}: SchoolAccessDialogProps) {
  const [memberships, setMemberships] = useState<UserSchoolMembership[]>([]);
  const [pendingMembership, setPendingMembership] = useState<{
    kind: 'remove' | 'primary';
    m: UserSchoolMembership;
  } | null>(null);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [addSchoolId, setAddSchoolId] = useState<string>('');

  const userId = user?.id ?? null;

  const reload = useCallback(async () => {
    if (!userId) return;
    setLoading(true);
    try {
      setMemberships(await listUserSchools(userId));
    } catch (err) {
      toast.error('Failed to load school access', {
        description: err instanceof Error ? err.message : 'Please try again.',
      });
    } finally {
      setLoading(false);
    }
  }, [userId]);

  useEffect(() => {
    if (userId) reload();
    else setMemberships([]);
  }, [userId, reload]);

  const grantedIds = new Set(memberships.map((m) => m.school_id));
  const hasPrimary = memberships.some((m) => m.is_primary);
  const available = schools.filter((s) => s.is_active && !grantedIds.has(s.school_id));

  const handleAdd = async () => {
    if (!userId || !addSchoolId) return;
    setBusy(true);
    try {
      // First school for a user with none yet becomes primary.
      await grantUserSchool(userId, {
        school_id: addSchoolId,
        school_role: 'member',
        is_primary: !hasPrimary,
      });
      toast.success('School access granted', {
        description: 'Applies after the user signs in again.',
      });
      setAddSchoolId('');
      await reload();
    } catch (err) {
      toast.error('Failed to grant access', {
        description: err instanceof Error ? err.message : 'Please try again.',
      });
    } finally {
      setBusy(false);
    }
  };

  const handleSetPrimary = async (m: UserSchoolMembership) => {
    if (!userId || m.is_primary) return;
    setBusy(true);
    try {
      await grantUserSchool(userId, {
        school_id: m.school_id,
        school_role: m.school_role,
        is_primary: true,
      });
      toast.success('Primary school updated', {
        description: 'Applies after the user signs in again.',
      });
      await reload();
    } catch (err) {
      toast.error('Failed to set primary', {
        description: err instanceof Error ? err.message : 'Please try again.',
      });
    } finally {
      setBusy(false);
    }
  };

  const handleRemove = async (m: UserSchoolMembership) => {
    if (!userId) return;
    setBusy(true);
    try {
      await revokeUserSchool(userId, m.school_id);
      toast.success('School access revoked', {
        description: 'Applies after the user signs in again.',
      });
      await reload();
    } catch (err) {
      toast.error('Failed to revoke access', {
        description: err instanceof Error ? err.message : 'Please try again.',
      });
    } finally {
      setBusy(false);
    }
  };

  const confirmMembership = async () => {
    const p = pendingMembership;
    if (!p) return;
    setPendingMembership(null);
    if (p.kind === 'remove') await handleRemove(p.m);
    else await handleSetPrimary(p.m);
  };

  return (
    <>
    <Dialog open={!!user} onOpenChange={(open) => !open && onOpenChange(false)}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>School Access</DialogTitle>
          <DialogDescription>
            Manage which schools <span className="font-medium">{user?.email}</span>{' '}
            can access.
          </DialogDescription>
        </DialogHeader>

        <div className="rounded-md bg-muted px-3 py-2 text-xs text-muted-foreground">
          Access changes apply after the user signs in again (their session token
          is refreshed on next login).
        </div>

        {/* Current memberships */}
        <div className="space-y-2">
          <Label>Current access</Label>
          {loading ? (
            <div className="flex items-center gap-2 text-sm text-muted-foreground py-2">
              <Loader2 className="h-4 w-4 animate-spin" /> Loading...
            </div>
          ) : memberships.length === 0 ? (
            <p className="text-sm text-muted-foreground py-2">
              No school access granted yet.
            </p>
          ) : (
            <ul className="space-y-1.5">
              {memberships.map((m) => (
                <li
                  key={m.id}
                  className="flex items-center justify-between gap-2 rounded-md border border-border px-3 py-2"
                >
                  <div className="flex items-center gap-2 min-w-0">
                    <span className="truncate text-sm text-foreground">
                      {m.school_name}
                    </span>
                    {m.is_primary && (
                      <Badge variant="secondary" className="shrink-0">
                        Primary
                      </Badge>
                    )}
                  </div>
                  <div className="flex items-center gap-1 shrink-0">
                    {!m.is_primary && (
                      <Button
                        variant="ghost"
                        size="sm"
                        disabled={busy}
                        onClick={() => setPendingMembership({ kind: 'primary', m })}
                        aria-label={`Set ${m.school_name} as primary`}
                      >
                        <Star className="h-4 w-4" />
                      </Button>
                    )}
                    <Button
                      variant="ghost"
                      size="sm"
                      disabled={busy}
                      onClick={() => setPendingMembership({ kind: 'remove', m })}
                      className="text-destructive focus:text-destructive"
                      aria-label={`Remove access to ${m.school_name}`}
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>

        {/* Add membership */}
        <div className="space-y-2">
          <Label>Grant access to a school</Label>
          <div className="flex items-center gap-2">
            <Select value={addSchoolId} onValueChange={setAddSchoolId}>
              <SelectTrigger aria-label="Select school to grant" className="flex-1">
                <SelectValue
                  placeholder={
                    loadingSchools ? 'Loading schools...' : 'Select a school'
                  }
                />
              </SelectTrigger>
              <SelectContent>
                {available.length === 0 ? (
                  <SelectItem value="__none__" disabled>
                    No more active schools
                  </SelectItem>
                ) : (
                  available.map((s) => (
                    <SelectItem key={s.school_id} value={s.school_id}>
                      {s.name}
                    </SelectItem>
                  ))
                )}
              </SelectContent>
            </Select>
            <Button onClick={handleAdd} disabled={!addSchoolId || busy}>
              <Plus className="h-4 w-4 mr-1" /> Grant
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>

    {pendingMembership && (
      <ConfirmActionDialog
        open={!!pendingMembership}
        onOpenChange={(o) => !o && setPendingMembership(null)}
        title={
          pendingMembership.kind === 'remove'
            ? 'Revoke school access?'
            : 'Set primary school?'
        }
        description={
          pendingMembership.kind === 'remove' ? (
            <>
              Remove access to{' '}
              <span className="font-semibold text-foreground">
                {pendingMembership.m.school_name}
              </span>
              . Applies on the user&apos;s next sign-in.
            </>
          ) : (
            <>
              Make{' '}
              <span className="font-semibold text-foreground">
                {pendingMembership.m.school_name}
              </span>{' '}
              the user&apos;s default school. Applies on their next sign-in.
            </>
          )
        }
        confirmLabel={pendingMembership.kind === 'remove' ? 'Revoke' : 'Set primary'}
        variant={pendingMembership.kind === 'remove' ? 'destructive' : 'default'}
        loading={busy}
        onConfirm={confirmMembership}
      />
    )}
    </>
  );
}
