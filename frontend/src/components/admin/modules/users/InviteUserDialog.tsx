'use client';

import { useState, type KeyboardEvent, type ClipboardEvent } from 'react';
import { X, Check, AlertTriangle, XCircle, Users } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { Checkbox } from '@/components/ui/checkbox';
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
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { cn } from '@/lib/utils';
import type { RoleResponse } from '@/lib/services/rbac.service';
import type { School } from '@/lib/services/schools.service';
import type { InviteEmailResult } from '@/lib/services/users.service';

export interface InviteFormValues {
  emails: string[];
  full_name: string;
  role_id: string;
  school_ids: string[];
}

interface InviteUserDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  roles: RoleResponse[];
  schools: School[];
  loadingSchools: boolean;
  submitting: boolean;
  /** Per-email results after a submit; null while composing. */
  results: InviteEmailResult[] | null;
  onSubmit: (values: InviteFormValues) => void;
  /** Clear results and return to the compose form ("Invite more"). */
  onReset: () => void;
}

const NO_ROLE = '__none__';
const MAX_EMAILS = 20;
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

function tokenize(raw: string): string[] {
  return raw
    .split(/[\s,;]+/)
    .map((s) => s.trim().toLowerCase())
    .filter(Boolean);
}

export function InviteUserDialog({
  open,
  onOpenChange,
  roles,
  schools,
  loadingSchools,
  submitting,
  results,
  onSubmit,
  onReset,
}: InviteUserDialogProps) {
  const [chips, setChips] = useState<string[]>([]);
  const [input, setInput] = useState('');
  const [fullName, setFullName] = useState('');
  const [roleId, setRoleId] = useState<string>(NO_ROLE);
  const [schoolIds, setSchoolIds] = useState<string[]>([]);

  const reset = () => {
    setChips([]);
    setInput('');
    setFullName('');
    setRoleId(NO_ROLE);
    setSchoolIds([]);
    onReset();
  };

  const handleOpenChange = (next: boolean) => {
    if (!next) reset();
    onOpenChange(next);
  };

  const addTokens = (raw: string) => {
    const tokens = tokenize(raw);
    if (!tokens.length) return;
    setChips((prev) =>
      Array.from(new Set([...prev, ...tokens])).slice(0, MAX_EMAILS),
    );
    setInput('');
  };

  const onInputKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (['Enter', ',', ';', ' ', 'Tab'].includes(e.key)) {
      if (input.trim()) {
        e.preventDefault();
        addTokens(input);
      }
    } else if (e.key === 'Backspace' && !input && chips.length) {
      setChips((prev) => prev.slice(0, -1));
    }
  };

  const onInputPaste = (e: ClipboardEvent<HTMLInputElement>) => {
    const text = e.clipboardData.getData('text');
    if (/[\s,;]/.test(text)) {
      e.preventDefault();
      addTokens(text);
    }
  };

  const removeChip = (email: string) =>
    setChips((prev) => prev.filter((c) => c !== email));

  const toggleSchool = (id: string) =>
    setSchoolIds((prev) =>
      prev.includes(id) ? prev.filter((s) => s !== id) : [...prev, id],
    );

  const validEmails = chips.filter((c) => EMAIL_RE.test(c));
  const invalidCount = chips.length - validEmails.length;
  const activeSchools = schools.filter((s) => s.is_active);

  const handleSubmit = () => {
    // Fold any half-typed token in first.
    const pending = tokenize(input);
    const finalChips = Array.from(new Set([...chips, ...pending])).slice(
      0,
      MAX_EMAILS,
    );
    const valid = finalChips.filter((c) => EMAIL_RE.test(c));
    if (!valid.length) return;
    setChips(finalChips);
    setInput('');
    onSubmit({
      emails: valid,
      full_name: fullName.trim(),
      role_id: roleId === NO_ROLE ? '' : roleId,
      school_ids: schoolIds,
    });
  };

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Invite users</DialogTitle>
          <DialogDescription>
            {results
              ? 'Invitation results — each recipient sets their own password to activate.'
              : 'Add one or more emails. Each recipient gets an invitation email and sets their own password.'}
          </DialogDescription>
        </DialogHeader>

        {results ? (
          <InviteResults results={results} />
        ) : (
          <div className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="invite-emails">
                Emails{' '}
                {validEmails.length > 0 && (
                  <span className="text-muted-foreground font-normal">
                    · {validEmails.length} recipient
                    {validEmails.length === 1 ? '' : 's'}
                  </span>
                )}
              </Label>
              <div className="flex flex-wrap gap-1.5 rounded-md border border-input bg-background p-2 focus-within:ring-2 focus-within:ring-ring">
                {chips.map((email) => {
                  const valid = EMAIL_RE.test(email);
                  return (
                    <Badge
                      key={email}
                      variant="secondary"
                      className={cn(
                        'gap-1 pl-2 pr-1 font-normal',
                        !valid &&
                          'bg-destructive/10 text-destructive border-destructive/30',
                      )}
                    >
                      {email}
                      <button
                        type="button"
                        onClick={() => removeChip(email)}
                        className="rounded-full p-0.5 hover:bg-foreground/10"
                        aria-label={`Remove ${email}`}
                      >
                        <X className="h-3 w-3" />
                      </button>
                    </Badge>
                  );
                })}
                <input
                  id="invite-emails"
                  className="flex-1 min-w-[8rem] bg-transparent text-sm outline-none placeholder:text-muted-foreground"
                  placeholder={
                    chips.length ? 'Add another…' : 'teacher@school.org, …'
                  }
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={onInputKeyDown}
                  onPaste={onInputPaste}
                  onBlur={() => input.trim() && addTokens(input)}
                  autoComplete="off"
                />
              </div>
              <p className="text-xs text-muted-foreground">
                Separate with commas, spaces, or new lines (max {MAX_EMAILS}).
                {invalidCount > 0 && (
                  <span className="text-destructive">
                    {' '}
                    {invalidCount} invalid — fix or remove.
                  </span>
                )}
              </p>
            </div>

            <div className="space-y-2">
              <Label htmlFor="invite-name">Full name (optional)</Label>
              <Input
                id="invite-name"
                placeholder="Jane Doe"
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
              />
            </div>

            <div className="grid grid-cols-1 gap-4">
              <div className="space-y-2">
                <Label>Platform role (optional)</Label>
                <Select value={roleId} onValueChange={setRoleId}>
                  <SelectTrigger aria-label="Select platform role">
                    <SelectValue placeholder="No role" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value={NO_ROLE}>No role</SelectItem>
                    {roles.map((role) => (
                      <SelectItem key={role.id} value={role.id}>
                        {role.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-2">
                <Label>School access (optional)</Label>
                <p className="text-xs text-muted-foreground">
                  Applied to every invited user. The first selected school
                  becomes their primary school.
                </p>
                <div className="max-h-40 overflow-y-auto rounded-md border border-border p-2 space-y-1">
                  {loadingSchools ? (
                    <p className="text-sm text-muted-foreground px-1 py-2">
                      Loading schools…
                    </p>
                  ) : activeSchools.length === 0 ? (
                    <p className="text-sm text-muted-foreground px-1 py-2">
                      No active schools available.
                    </p>
                  ) : (
                    activeSchools.map((school) => (
                      <label
                        key={school.school_id}
                        className="flex items-center gap-2 rounded px-1 py-1.5 hover:bg-muted cursor-pointer"
                      >
                        <Checkbox
                          checked={schoolIds.includes(school.school_id)}
                          onCheckedChange={() => toggleSchool(school.school_id)}
                        />
                        <span className="text-sm text-foreground">
                          {school.name}
                        </span>
                      </label>
                    ))
                  )}
                </div>
              </div>
            </div>
          </div>
        )}

        <DialogFooter>
          {results ? (
            <>
              <Button variant="outline" onClick={onReset}>
                <Users className="h-4 w-4 mr-2" />
                Invite more
              </Button>
              <Button onClick={() => handleOpenChange(false)}>Done</Button>
            </>
          ) : (
            <>
              <Button variant="outline" onClick={() => handleOpenChange(false)}>
                Cancel
              </Button>
              <Button
                onClick={handleSubmit}
                disabled={validEmails.length === 0 || submitting}
              >
                {submitting
                  ? 'Sending…'
                  : `Send ${validEmails.length || ''} invitation${
                      validEmails.length === 1 ? '' : 's'
                    }`.trim()}
              </Button>
            </>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function InviteResults({ results }: { results: InviteEmailResult[] }) {
  const invited = results.filter((r) => r.status === 'invited').length;
  const failed = results.length - invited;
  return (
    <div className="space-y-3">
      <div className="flex gap-2 text-sm">
        <Badge className="bg-success/15 text-success border-success/30">
          {invited} invited
        </Badge>
        {failed > 0 && (
          <Badge variant="secondary" className="bg-muted text-muted-foreground">
            {failed} skipped/failed
          </Badge>
        )}
      </div>
      <div className="max-h-72 space-y-1.5 overflow-y-auto">
        {results.map((r) => (
          <div
            key={r.email}
            className="flex items-center justify-between gap-3 rounded-md border border-border px-3 py-2 text-sm"
          >
            <span className="truncate">{r.email}</span>
            <ResultBadge r={r} />
          </div>
        ))}
      </div>
    </div>
  );
}

function ResultBadge({ r }: { r: InviteEmailResult }) {
  if (r.status === 'invited') {
    if (r.provisioned === false) {
      return (
        <span className="flex items-center gap-1 whitespace-nowrap text-warning">
          <AlertTriangle className="h-3.5 w-3.5" />
          Invited · role/school failed
        </span>
      );
    }
    return (
      <span className="flex items-center gap-1 whitespace-nowrap text-success">
        <Check className="h-3.5 w-3.5" />
        Invited
      </span>
    );
  }
  if (r.status === 'already_exists') {
    return (
      <span className="flex items-center gap-1 whitespace-nowrap text-muted-foreground">
        <AlertTriangle className="h-3.5 w-3.5" />
        Already exists
      </span>
    );
  }
  return (
    <span className="flex items-center gap-1 whitespace-nowrap text-destructive">
      <XCircle className="h-3.5 w-3.5" />
      Failed
    </span>
  );
}
