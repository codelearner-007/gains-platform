import { format } from 'date-fns';
import {
  X,
  MoreHorizontal,
  Ban,
  Trash2,
  Mail,
  Key,
  CheckCircle,
  Shield,
  Building2,
} from 'lucide-react';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Checkbox } from '@/components/ui/checkbox';
import { cn } from '@/lib/utils';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { UserStatusBadge } from './UserStatusBadge';
import { UserPagination } from './UserPagination';
import type { UserWithRoles, UserFilters } from '@/lib/services/rbac.service';

interface UserTableProps {
  users: UserWithRoles[];
  filters: UserFilters;
  total: number;
  totalPages: number;
  loading: boolean;
  error: string | null;
  actionLoading: string | null;
  hasActiveFilters: boolean;
  hasAnyAction: boolean;
  canAssignRoles: boolean;
  canUpdateAll: boolean;
  canDeleteAll: boolean;
  isSuperAdmin: (user: UserWithRoles) => boolean;
  /** Whether bulk selection is available (any bulk-capable permission). */
  selectable: boolean;
  selectedIds: Set<string>;
  onToggleSelect: (id: string) => void;
  onSetSelection: (ids: string[]) => void;
  onSetPage: (page: number) => void;
  onBanUser: (user: UserWithRoles) => void;
  onUnbanUser: (user: UserWithRoles) => void;
  onDeleteUser: (user: UserWithRoles) => void;
  onResendVerification: (user: UserWithRoles) => void;
  onResetPassword: (user: UserWithRoles) => void;
  onAssignRole: (user: UserWithRoles) => void;
  onRemoveRole: (user: UserWithRoles, roleId: string) => void;
  onManageSchools: (user: UserWithRoles) => void;
}

function formatDate(dateString: string | null | undefined): string {
  if (!dateString) return 'Never';
  return format(new Date(dateString), 'MMM d, yyyy');
}

function TableLoadingSkeleton() {
  return (
    <div className="p-8 space-y-4" role="status" aria-label="Loading users">
      {Array.from({ length: 8 }).map((_, i) => (
        <div key={i} className="h-16 rounded bg-muted animate-pulse" />
      ))}
      <span className="sr-only">Loading users...</span>
    </div>
  );
}

function TableError({ message }: { message: string }) {
  return (
    <div className="p-8 text-center" role="alert">
      <p className="text-sm text-destructive">{message}</p>
    </div>
  );
}

function TableEmpty({ hasActiveFilters }: { hasActiveFilters: boolean }) {
  return (
    <div className="p-12 text-center">
      <p className="text-sm font-medium text-muted-foreground">No users found</p>
      <p className="text-xs text-muted-foreground mt-1">
        {hasActiveFilters ? 'Try adjusting your filters' : 'No users in the system'}
      </p>
    </div>
  );
}

export function UserTable({
  users,
  filters,
  total,
  totalPages,
  loading,
  error,
  actionLoading,
  hasActiveFilters,
  hasAnyAction,
  canAssignRoles,
  canUpdateAll,
  canDeleteAll,
  isSuperAdmin,
  selectable,
  selectedIds,
  onToggleSelect,
  onSetSelection,
  onSetPage,
  onBanUser,
  onUnbanUser,
  onDeleteUser,
  onResendVerification,
  onResetPassword,
  onAssignRole,
  onManageSchools,
  onRemoveRole,
}: UserTableProps) {
  function renderContent() {
    if (loading) return <TableLoadingSkeleton />;
    if (error) return <TableError message={error} />;
    if (users.length === 0) return <TableEmpty hasActiveFilters={hasActiveFilters} />;

    // Selection covers only non-superadmin rows (superadmins are protected).
    const selectableIds = users.filter((u) => !isSuperAdmin(u)).map((u) => u.id);
    const allSelected =
      selectableIds.length > 0 && selectableIds.every((id) => selectedIds.has(id));
    const someSelected = selectableIds.some((id) => selectedIds.has(id));
    const headerChecked: boolean | 'indeterminate' = allSelected
      ? true
      : someSelected
        ? 'indeterminate'
        : false;

    return (
      <>
        {/* Screen reader announcement */}
        <div className="sr-only" role="status" aria-live="polite">
          {total} users found. Showing page {filters.page} of {totalPages}.
        </div>

        <div className="overflow-x-auto">
          <Table aria-label="Users list">
            <TableHeader>
              <TableRow className="bg-muted/40">
                {selectable && (
                  <TableHead scope="col" className="w-[44px]">
                    <Checkbox
                      checked={headerChecked}
                      onCheckedChange={() =>
                        onSetSelection(allSelected ? [] : selectableIds)
                      }
                      aria-label="Select all users on this page"
                      disabled={selectableIds.length === 0}
                    />
                  </TableHead>
                )}
                <TableHead scope="col" className="font-semibold">Email</TableHead>
                <TableHead scope="col" className="font-semibold">Status</TableHead>
                <TableHead scope="col" className="font-semibold">Roles</TableHead>
                <TableHead scope="col" className="font-semibold">Schools</TableHead>
                <TableHead scope="col" className="font-semibold">Last Sign In</TableHead>
                <TableHead scope="col" className="font-semibold">Created</TableHead>
                {hasAnyAction && (
                  <TableHead scope="col" className="font-semibold w-[50px]">
                    <span className="sr-only">Actions</span>
                  </TableHead>
                )}
              </TableRow>
            </TableHeader>
            <TableBody>
              {users.map((user) => (
                <TableRow
                  key={user.id}
                  className={cn(
                    'hover:bg-muted/30',
                    selectedIds.has(user.id) && 'bg-primary/5',
                  )}
                >
                  {selectable && (
                    <TableCell>
                      {isSuperAdmin(user) ? (
                        <span
                          className="inline-flex"
                          title="Superadmin — protected"
                        >
                          <Checkbox disabled aria-label="Protected user" />
                        </span>
                      ) : (
                        <Checkbox
                          checked={selectedIds.has(user.id)}
                          onCheckedChange={() => onToggleSelect(user.id)}
                          aria-label={`Select ${user.email}`}
                        />
                      )}
                    </TableCell>
                  )}
                  <TableCell>
                    <div>
                      <p className="font-medium text-sm">{user.email}</p>
                      <p className="text-xs text-muted-foreground font-mono">
                        {user.id.slice(0, 8)}
                      </p>
                    </div>
                  </TableCell>
                  <TableCell>
                    <UserStatusBadge user={user} />
                  </TableCell>
                  <TableCell>
                    <div className="flex flex-wrap gap-1">
                      {user.roles.length === 0 ? (
                        <span className="text-xs text-muted-foreground">No roles</span>
                      ) : (
                        user.roles.map((ur) => (
                          <Badge
                            key={ur.id}
                            variant="secondary"
                            className="bg-primary/10 text-primary border-primary/20 gap-1"
                          >
                            {ur.role.name}
                            {canAssignRoles && !isSuperAdmin(user) && (
                              <Button
                                variant="ghost"
                                size="icon"
                                onClick={() => onRemoveRole(user, ur.role_id)}
                                disabled={actionLoading === user.id}
                                className="h-4 w-4 hover:bg-primary/20 rounded-full p-0 transition-colors"
                                aria-label={`Remove ${ur.role.name} role from ${user.email}`}
                              >
                                <X className="h-2.5 w-2.5" />
                              </Button>
                            )}
                          </Badge>
                        ))
                      )}
                    </div>
                  </TableCell>
                  <TableCell>
                    <div className="flex flex-wrap gap-1">
                      {!user.schools || user.schools.length === 0 ? (
                        <span className="text-xs text-muted-foreground">—</span>
                      ) : (
                        <>
                          {user.schools.slice(0, 2).map((s) => (
                            <Badge
                              key={s.school_id}
                              variant="secondary"
                              className="gap-1 font-normal"
                              title={
                                s.is_primary
                                  ? `${s.school_name} (primary)`
                                  : s.school_name
                              }
                            >
                              {s.school_short_name || s.school_name}
                              {s.is_primary && (
                                <span className="text-[10px] text-muted-foreground">
                                  ★
                                </span>
                              )}
                            </Badge>
                          ))}
                          {user.schools.length > 2 && (
                            <Badge variant="secondary" className="font-normal">
                              +{user.schools.length - 2}
                            </Badge>
                          )}
                        </>
                      )}
                    </div>
                  </TableCell>
                  <TableCell className="text-sm text-muted-foreground">
                    {formatDate(user.last_sign_in_at)}
                  </TableCell>
                  <TableCell className="text-sm text-muted-foreground">
                    {formatDate(user.created_at)}
                  </TableCell>
                  {hasAnyAction && (
                    <TableCell>
                      {isSuperAdmin(user) ? (
                        <div className="text-xs text-muted-foreground italic px-2">
                          Protected
                        </div>
                      ) : (
                        <DropdownMenu>
                          <DropdownMenuTrigger asChild>
                            <Button
                              variant="ghost"
                              size="icon"
                              className="h-8 w-8"
                              disabled={actionLoading === user.id}
                              aria-label={`Actions for ${user.email}`}
                            >
                              <MoreHorizontal className="h-4 w-4" />
                            </Button>
                          </DropdownMenuTrigger>
                          <DropdownMenuContent align="end">
                            {canAssignRoles && (
                              <>
                                <DropdownMenuItem onClick={() => onAssignRole(user)}>
                                  <Shield className="h-4 w-4 mr-2" />
                                  Assign Role
                                </DropdownMenuItem>
                                <DropdownMenuItem onClick={() => onManageSchools(user)}>
                                  <Building2 className="h-4 w-4 mr-2" />
                                  School Access
                                </DropdownMenuItem>
                              </>
                            )}
                            {canUpdateAll && (
                              <>
                                {canAssignRoles && <DropdownMenuSeparator />}
                                {!user.email_confirmed_at && (
                                  <DropdownMenuItem
                                    onClick={() => onResendVerification(user)}
                                  >
                                    <Mail className="h-4 w-4 mr-2" />
                                    Resend Invitation
                                  </DropdownMenuItem>
                                )}
                                <DropdownMenuItem
                                  onClick={() => onResetPassword(user)}
                                >
                                  <Key className="h-4 w-4 mr-2" />
                                  Reset Password
                                </DropdownMenuItem>
                                <DropdownMenuSeparator />
                                {user.is_banned ? (
                                  <DropdownMenuItem
                                    onClick={() => onUnbanUser(user)}
                                  >
                                    <CheckCircle className="h-4 w-4 mr-2" />
                                    Unban User
                                  </DropdownMenuItem>
                                ) : (
                                  <DropdownMenuItem
                                    onClick={() => onBanUser(user)}
                                  >
                                    <Ban className="h-4 w-4 mr-2" />
                                    Ban User
                                  </DropdownMenuItem>
                                )}
                              </>
                            )}
                            {canDeleteAll && (
                              <DropdownMenuItem
                                onClick={() => onDeleteUser(user)}
                                className="text-destructive focus:text-destructive"
                              >
                                <Trash2 className="h-4 w-4 mr-2" />
                                Delete User
                              </DropdownMenuItem>
                            )}
                          </DropdownMenuContent>
                        </DropdownMenu>
                      )}
                    </TableCell>
                  )}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>

        <UserPagination
          page={filters.page}
          pageSize={filters.page_size}
          total={total}
          totalPages={totalPages}
          loading={loading}
          onSetPage={onSetPage}
        />
      </>
    );
  }

  return (
    <Card className="border-border shadow-sm">
      <CardContent className="p-0">
        {renderContent()}
      </CardContent>
    </Card>
  );
}
