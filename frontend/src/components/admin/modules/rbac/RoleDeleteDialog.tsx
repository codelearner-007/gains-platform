'use client';

import { useState } from 'react';
import { Loader2, Trash2 } from 'lucide-react';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from '@/components/ui/alert-dialog';
import { Button } from '@/components/ui/button';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import { toast } from 'sonner';
import { deleteRole, type RoleResponse } from '@/lib/services/rbac.service';

interface RoleDeleteDialogProps {
  role: RoleResponse;
  onSuccess: () => void;
  disabled?: boolean;
  disabledReason?: string;
}

export function RoleDeleteDialog({ role, onSuccess, disabled = false, disabledReason }: RoleDeleteDialogProps) {
  const [open, setOpen] = useState(false);
  const [deleting, setDeleting] = useState(false);

  const handleDelete = async () => {
    try {
      setDeleting(true);
      await deleteRole(role.id);
      toast('Role deleted', { description: `Role "${role.name}" has been deleted successfully.` });
      setOpen(false);
      onSuccess();
    } catch (err) {
      console.error('Error deleting role:', err);
      toast('Failed to delete role', {
        description: err instanceof Error ? err.message : 'Please try again.',
      });
    } finally {
      setDeleting(false);
    }
  };

  // System roles cannot be deleted
  const isSystemRole = role.name === 'super_admin' || role.name === 'user';

  // Determine tooltip message
  const getTooltipMessage = () => {
    if (isSystemRole) {
      return 'System roles (super_admin, user) cannot be deleted';
    }
    if (disabledReason) {
      return disabledReason;
    }
    if (disabled) {
      return 'You do not have permission to delete this role';
    }
    return 'Delete role';
  };

  const isDisabled = disabled || isSystemRole;

  return (
    <AlertDialog open={open} onOpenChange={setOpen}>
      <TooltipProvider>
        <Tooltip>
          <TooltipTrigger asChild>
            <span className="inline-block">
              <AlertDialogTrigger asChild>
                <Button
                  variant="ghost"
                  size="icon"
                  disabled={isDisabled}
                >
                  <Trash2 className="h-4 w-4" />
                </Button>
              </AlertDialogTrigger>
            </span>
          </TooltipTrigger>
          <TooltipContent>
            <p>{getTooltipMessage()}</p>
          </TooltipContent>
        </Tooltip>
      </TooltipProvider>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Delete Role: {role.name}?</AlertDialogTitle>
          <AlertDialogDescription>
            This action cannot be undone. This will permanently delete the role &quot;{role.name}&quot; and remove it from all users.
            {isSystemRole && (
              <span className="block mt-2 text-destructive font-medium">
                System roles (super_admin, user) cannot be deleted.
              </span>
            )}
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel disabled={deleting}>Cancel</AlertDialogCancel>
          <AlertDialogAction
            onClick={handleDelete}
            disabled={deleting}
            className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
          >
            {deleting && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
            Delete Role
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
