'use client';

import { useState, useEffect } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { Loader2, Pencil } from 'lucide-react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import { toast } from 'sonner';
import { roleUpdateSchema, type RoleUpdateInput } from '@/lib/schemas/rbac.schema';
import { updateRole, type RoleResponse } from '@/lib/services/rbac.service';

interface RoleEditDialogProps {
  role: RoleResponse;
  onSuccess: () => void;
  disabled?: boolean;
  disabledReason?: string;
}

export function RoleEditDialog({ role, onSuccess, disabled = false, disabledReason }: RoleEditDialogProps) {
  const [open, setOpen] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  const {
    register,
    handleSubmit,
    formState: { errors },
    reset,
  } = useForm<RoleUpdateInput>({
    resolver: zodResolver(roleUpdateSchema),
    defaultValues: {
      name: role.name,
      description: role.description || '',
      hierarchy_level: role.hierarchy_level,
    },
  });

  useEffect(() => {
    if (open) {
      reset({
        name: role.name,
        description: role.description || '',
        hierarchy_level: role.hierarchy_level,
      });
    }
  }, [open, role, reset]);

  const onSubmit = async (data: RoleUpdateInput) => {
    try {
      setSubmitting(true);
      await updateRole(role.id, data);
      toast('Role updated', { description: `Role "${data.name || role.name}" has been updated successfully.` });
      setOpen(false);
      onSuccess();
    } catch (err) {
      console.error('Error updating role:', err);
      toast('Failed to update role', {
        description: err instanceof Error ? err.message : 'Please try again.',
      });
    } finally {
      setSubmitting(false);
    }
  };

  // System roles cannot be edited
  const isSystemRole = role.name === 'super_admin' || role.name === 'user';

  // Determine tooltip message
  const getTooltipMessage = () => {
    if (isSystemRole) {
      return 'System roles (super_admin, user) cannot be edited';
    }
    if (disabledReason) {
      return disabledReason;
    }
    if (disabled) {
      return 'You do not have permission to edit this role';
    }
    return 'Edit role';
  };

  const isDisabled = disabled || isSystemRole;

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <TooltipProvider>
        <Tooltip>
          <TooltipTrigger asChild>
            <span className="inline-block">
              <DialogTrigger asChild>
                <Button
                  variant="ghost"
                  size="icon"
                  disabled={isDisabled}
                >
                  <Pencil className="h-4 w-4" />
                </Button>
              </DialogTrigger>
            </span>
          </TooltipTrigger>
          <TooltipContent>
            <p>{getTooltipMessage()}</p>
          </TooltipContent>
        </Tooltip>
      </TooltipProvider>
      <DialogContent>
        <form onSubmit={handleSubmit(onSubmit)}>
          <DialogHeader>
            <DialogTitle>Edit Role</DialogTitle>
            <DialogDescription>
              Update role details. Note: System roles (super_admin, user) cannot be edited.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label htmlFor="name">Role Name *</Label>
              <Input
                id="name"
                placeholder="e.g., manager, developer"
                {...register('name')}
                aria-invalid={!!errors.name}
              />
              {errors.name && (
                <p className="text-sm text-destructive">{errors.name.message}</p>
              )}
              <p className="text-xs text-muted-foreground">
                Lowercase with underscores only
              </p>
            </div>

            <div className="space-y-2">
              <Label htmlFor="description">Description</Label>
              <Textarea
                id="description"
                placeholder="Optional role description"
                {...register('description')}
              />
              {errors.description && (
                <p className="text-sm text-destructive">{errors.description.message}</p>
              )}
            </div>

            <div className="space-y-2">
              <Label htmlFor="hierarchy_level">Hierarchy Level *</Label>
              <Input
                id="hierarchy_level"
                type="number"
                placeholder="100"
                {...register('hierarchy_level', { valueAsNumber: true })}
              />
              {errors.hierarchy_level && (
                <p className="text-sm text-destructive">{errors.hierarchy_level.message}</p>
              )}
              <p className="text-xs text-muted-foreground">
                Higher values = more privileged. System roles: super_admin (10000), user (100)
              </p>
            </div>
          </div>

          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => setOpen(false)}
              disabled={submitting}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={submitting}>
              {submitting && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
              Update Role
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
