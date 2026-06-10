'use client';

import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
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
import type { RoleResponse } from '@/lib/services/rbac.service';
import type { School } from '@/lib/services/schools.service';

export interface InviteFormValues {
  email: string;
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
  onSubmit: (values: InviteFormValues) => void;
}

const NO_ROLE = '__none__';

export function InviteUserDialog({
  open,
  onOpenChange,
  roles,
  schools,
  loadingSchools,
  submitting,
  onSubmit,
}: InviteUserDialogProps) {
  const [email, setEmail] = useState('');
  const [fullName, setFullName] = useState('');
  const [roleId, setRoleId] = useState<string>(NO_ROLE);
  const [schoolIds, setSchoolIds] = useState<string[]>([]);

  const reset = () => {
    setEmail('');
    setFullName('');
    setRoleId(NO_ROLE);
    setSchoolIds([]);
  };

  const handleOpenChange = (next: boolean) => {
    if (!next) reset();
    onOpenChange(next);
  };

  const toggleSchool = (id: string) => {
    setSchoolIds((prev) =>
      prev.includes(id) ? prev.filter((s) => s !== id) : [...prev, id],
    );
  };

  const emailValid = /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim());

  const handleSubmit = () => {
    if (!emailValid) return;
    onSubmit({
      email: email.trim(),
      full_name: fullName.trim(),
      role_id: roleId === NO_ROLE ? '' : roleId,
      school_ids: schoolIds,
    });
  };

  const activeSchools = schools.filter((s) => s.is_active);

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Invite User</DialogTitle>
          <DialogDescription>
            Send an invitation email. The user sets their own password to
            activate the account.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="invite-email">Email</Label>
            <Input
              id="invite-email"
              type="email"
              autoComplete="off"
              placeholder="teacher@school.org"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
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
              The first selected school becomes the user&apos;s primary school.
            </p>
            <div className="max-h-44 overflow-y-auto rounded-md border border-border p-2 space-y-1">
              {loadingSchools ? (
                <p className="text-sm text-muted-foreground px-1 py-2">
                  Loading schools...
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
                    <span className="text-sm text-foreground">{school.name}</span>
                  </label>
                ))
              )}
            </div>
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => handleOpenChange(false)}>
            Cancel
          </Button>
          <Button onClick={handleSubmit} disabled={!emailValid || submitting}>
            {submitting ? 'Sending...' : 'Send Invitation'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
