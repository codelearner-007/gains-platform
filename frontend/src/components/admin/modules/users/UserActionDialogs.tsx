import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
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
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import type { UserWithRoles, RoleResponse } from '@/lib/services/rbac.service';
import type { AssignRoleDialogState } from './useUserManagement';

interface UserActionDialogsProps {
  // Assign Role Dialog
  assignRoleDialog: AssignRoleDialogState;
  onAssignRoleDialogChange: (state: AssignRoleDialogState) => void;
  onAssignRole: () => void;
  roles: RoleResponse[];

  // Ban Dialog
  banDialog: UserWithRoles | null;
  onBanDialogChange: (user: UserWithRoles | null) => void;
  onBanUser: (user: UserWithRoles) => void;

  // Delete Dialog
  deleteDialog: UserWithRoles | null;
  onDeleteDialogChange: (user: UserWithRoles | null) => void;
  onDeleteUser: (user: UserWithRoles) => void;

  // Shared
  actionLoading: string | null;
}

export function UserActionDialogs({
  assignRoleDialog,
  onAssignRoleDialogChange,
  onAssignRole,
  roles,
  banDialog,
  onBanDialogChange,
  onBanUser,
  deleteDialog,
  onDeleteDialogChange,
  onDeleteUser,
  actionLoading,
}: UserActionDialogsProps) {
  return (
    <>
      {/* Assign Role Dialog */}
      <Dialog
        open={!!assignRoleDialog.user}
        onOpenChange={(open) =>
          !open && onAssignRoleDialogChange({ user: null, roleId: '' })
        }
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Assign Role</DialogTitle>
            <DialogDescription>
              Assign a role to{' '}
              <span className="font-medium">{assignRoleDialog.user?.email}</span>
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-3">
            <Label>Role</Label>
            <Select
              value={assignRoleDialog.roleId}
              onValueChange={(value) =>
                onAssignRoleDialogChange({ ...assignRoleDialog, roleId: value })
              }
            >
              <SelectTrigger aria-label="Select role to assign">
                <SelectValue placeholder="Select a role" />
              </SelectTrigger>
              <SelectContent>
                {roles.map((role) => (
                  <SelectItem key={role.id} value={role.id}>
                    {role.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => onAssignRoleDialogChange({ user: null, roleId: '' })}
            >
              Cancel
            </Button>
            <Button
              onClick={onAssignRole}
              disabled={!assignRoleDialog.roleId || !!actionLoading}
            >
              Assign
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Ban User Dialog */}
      <AlertDialog
        open={!!banDialog}
        onOpenChange={(open) => !open && onBanDialogChange(null)}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Ban User?</AlertDialogTitle>
            <AlertDialogDescription>
              This will ban{' '}
              <span className="font-medium">{banDialog?.email}</span> from
              accessing the system. You can unban them later.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => banDialog && onBanUser(banDialog)}
              disabled={!!actionLoading}
              className="bg-destructive hover:bg-destructive/90"
            >
              Ban User
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Delete User Dialog */}
      <AlertDialog
        open={!!deleteDialog}
        onOpenChange={(open) => !open && onDeleteDialogChange(null)}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete User?</AlertDialogTitle>
            <AlertDialogDescription>
              This will permanently delete{' '}
              <span className="font-medium">{deleteDialog?.email}</span> and all
              associated data. This action cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => deleteDialog && onDeleteUser(deleteDialog)}
              disabled={!!actionLoading}
              className="bg-destructive hover:bg-destructive/90"
            >
              Delete Permanently
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}
