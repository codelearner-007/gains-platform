'use client';

import { useState, useEffect, useCallback } from 'react';
import { toast } from 'sonner';
import { useAdminClaims } from '@/components/admin/AdminClaimsContext';
import { hasPermission } from '@/lib/utils/rbac';
import {
  listRoles,
  getUserStats,
  listUsersWithRoles,
  banUser,
  unbanUser,
  deleteUser,
  resendVerificationEmail,
  sendPasswordResetEmail,
  assignRoleToUser,
  removeRoleFromUser,
  type UserWithRoles,
  type UserStats,
  type UserFilters,
  type RoleResponse,
} from '@/lib/services/rbac.service';
import { listSchools, type School } from '@/lib/services/schools.service';
import {
  inviteUsers,
  bulkUserAction,
  type InviteEmailResult,
  type BulkActionResult,
  type BulkUserAction,
} from '@/lib/services/users.service';
import type { InviteFormValues } from './InviteUserDialog';
import { useDebounce } from '@/hooks/useDebounce';

export interface AssignRoleDialogState {
  user: UserWithRoles | null;
  roleId: string;
}

/** A per-row action awaiting explicit confirmation. */
export type PendingUserAction =
  | { kind: 'unban' | 'resend' | 'reset'; user: UserWithRoles }
  | { kind: 'remove-role'; user: UserWithRoles; roleId: string; roleName: string };

export function useUserManagement() {
  // Core data state
  const [users, setUsers] = useState<UserWithRoles[]>([]);
  const [roles, setRoles] = useState<RoleResponse[]>([]);
  const [schools, setSchools] = useState<School[]>([]);
  const [loadingSchools, setLoadingSchools] = useState(false);
  const [stats, setStats] = useState<UserStats | null>(null);

  // Pagination state
  const [totalPages, setTotalPages] = useState(1);
  const [total, setTotal] = useState(0);

  // Filter state
  const [filters, setFilters] = useState<UserFilters>({
    page: 1,
    page_size: 20,
  });
  const [searchQuery, setSearchQuery] = useState('');
  const debouncedSearch = useDebounce(searchQuery, 300);

  // Loading state
  const [loading, setLoading] = useState(true);
  const [loadingStats, setLoadingStats] = useState(true);
  const [loadingRoles, setLoadingRoles] = useState(true);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Dialog state
  const [assignRoleDialog, setAssignRoleDialog] = useState<AssignRoleDialogState>({
    user: null,
    roleId: '',
  });
  const [deleteDialog, setDeleteDialog] = useState<UserWithRoles | null>(null);
  const [banDialog, setBanDialog] = useState<UserWithRoles | null>(null);
  const [inviteOpen, setInviteOpen] = useState(false);
  const [inviteSubmitting, setInviteSubmitting] = useState(false);
  const [inviteResults, setInviteResults] = useState<InviteEmailResult[] | null>(null);
  const [schoolAccessUser, setSchoolAccessUser] = useState<UserWithRoles | null>(null);

  // Bulk selection + bulk-action state
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [bulkLoading, setBulkLoading] = useState(false);
  const [bulkResults, setBulkResults] = useState<{
    action: BulkUserAction;
    results: BulkActionResult[];
  } | null>(null);

  // A per-row action awaiting explicit confirmation.
  const [pendingAction, setPendingAction] = useState<PendingUserAction | null>(null);

  // Permission checks
  const claims = useAdminClaims();
  const canAssignRoles = hasPermission(claims.permissions, 'users:assign_roles');
  const canUpdateAll = hasPermission(claims.permissions, 'users:update_all');
  const canDeleteAll = hasPermission(claims.permissions, 'users:delete_all');
  const hasAnyAction = canAssignRoles || canUpdateAll || canDeleteAll;

  // Helper: check if user is superadmin
  const isSuperAdmin = useCallback((user: UserWithRoles): boolean => {
    return user.roles.some((role) => role.role.name === 'super_admin');
  }, []);

  // Sync debounced search into filters
  useEffect(() => {
    setFilters((prev) => ({
      ...prev,
      search: debouncedSearch || undefined,
      page: 1,
    }));
  }, [debouncedSearch]);

  // Load stats
  useEffect(() => {
    async function loadStats() {
      try {
        setLoadingStats(true);
        const data = await getUserStats();
        setStats(data);
      } catch (err) {
        toast.error('Failed to load user statistics');
        console.error('Failed to load stats:', err);
      } finally {
        setLoadingStats(false);
      }
    }

    loadStats();
  }, []);

  // Load roles
  useEffect(() => {
    async function loadRoles() {
      try {
        setLoadingRoles(true);
        const data = await listRoles();
        setRoles(data.filter((r) => r.name !== 'super_admin'));
      } catch (err) {
        toast.error('Failed to load roles');
        console.error('Failed to load roles:', err);
      } finally {
        setLoadingRoles(false);
      }
    }

    loadRoles();
  }, []);

  // Load schools (for invite + school-access pickers). Only the persona that
  // can manage memberships needs them.
  useEffect(() => {
    if (!canAssignRoles) return;
    let cancelled = false;
    async function loadSchools() {
      try {
        setLoadingSchools(true);
        const data = await listSchools();
        if (!cancelled) setSchools(data);
      } catch (err) {
        console.error('Failed to load schools:', err);
      } finally {
        if (!cancelled) setLoadingSchools(false);
      }
    }
    loadSchools();
    return () => {
      cancelled = true;
    };
  }, [canAssignRoles]);

  // Load users
  useEffect(() => {
    async function loadUsers() {
      try {
        setLoading(true);
        setError(null);

        const response = await listUsersWithRoles(filters);

        setUsers(response.items);
        setTotalPages(response.total_pages);
        setTotal(response.total);
      } catch (err) {
        const message = err instanceof Error ? err.message : 'Failed to load users';
        setError(message);
        toast.error('Failed to load users', { description: 'Please try again.' });
        console.error('Error loading users:', err);
      } finally {
        setLoading(false);
      }
    }

    loadUsers();
  }, [filters]);

  // Filter handlers
  const handleFilterChange = useCallback(
    (key: keyof UserFilters, value: string | number | boolean | undefined) => {
      if (key === 'search') {
        // Search is handled via debounce
        setSearchQuery((value as string) || '');
        return;
      }
      setFilters((prev) => ({
        ...prev,
        [key]: value === '' || value === 'all' ? undefined : value,
        page: 1,
      }));
    },
    []
  );

  const handleRemoveFilter = useCallback((key: keyof UserFilters) => {
    if (key === 'search') {
      setSearchQuery('');
      return;
    }
    setFilters((prev) => {
      const newFilters = { ...prev };
      delete newFilters[key];
      return { ...newFilters, page: 1 };
    });
  }, []);

  const handleClearAllFilters = useCallback(() => {
    setSearchQuery('');
    setFilters((prev) => ({
      page: 1,
      page_size: prev.page_size,
    }));
  }, []);

  const setPage = useCallback((page: number) => {
    setFilters((prev) => ({ ...prev, page }));
  }, []);

  // Reload trigger
  const reloadUsers = useCallback(() => {
    setFilters((prev) => ({ ...prev }));
  }, []);

  // Clear row selection whenever the visible page / filter set changes
  // (selection is per-page; carrying it across pages would be misleading).
  useEffect(() => {
    setSelectedIds(new Set());
  }, [filters]);

  // Computed active filters (including search from local state)
  const activeFilters = [
    ...Object.entries(filters).filter(
      ([key, value]) =>
        value !== undefined && key !== 'page' && key !== 'page_size' && key !== 'search' && value !== ''
    ),
    ...(searchQuery ? [['search', searchQuery] as [string, string]] : []),
  ];

  const hasActiveFilters = activeFilters.length > 0;

  // Action handlers
  const handleBanUser = useCallback(
    async (user: UserWithRoles) => {
      try {
        setActionLoading(user.id);
        await banUser(user.id);
        toast.success('User banned', { description: `${user.email} has been banned.` });
        reloadUsers();
        setBanDialog(null);
      } catch (err) {
        toast.error('Failed to ban user', {
          description: err instanceof Error ? err.message : 'Please try again.',
        });
      } finally {
        setActionLoading(null);
      }
    },
    [reloadUsers]
  );

  const handleUnbanUser = useCallback(
    async (user: UserWithRoles) => {
      try {
        setActionLoading(user.id);
        await unbanUser(user.id);
        toast.success('User unbanned', { description: `${user.email} has been unbanned.` });
        reloadUsers();
      } catch (err) {
        toast.error('Failed to unban user', {
          description: err instanceof Error ? err.message : 'Please try again.',
        });
      } finally {
        setActionLoading(null);
      }
    },
    [reloadUsers]
  );

  const handleDeleteUser = useCallback(
    async (user: UserWithRoles) => {
      try {
        setActionLoading(user.id);
        await deleteUser(user.id);
        toast.success('User deleted', {
          description: `${user.email} has been deleted permanently.`,
        });
        reloadUsers();
        setDeleteDialog(null);
      } catch (err) {
        toast.error('Failed to delete user', {
          description: err instanceof Error ? err.message : 'Please try again.',
        });
      } finally {
        setActionLoading(null);
      }
    },
    [reloadUsers]
  );

  const handleResendVerification = useCallback(async (user: UserWithRoles) => {
    try {
      setActionLoading(user.id);
      await resendVerificationEmail(user.id);
      toast.success('Invitation resent', { description: `Sent to ${user.email}` });
    } catch (err) {
      toast.error('Failed to resend invitation', {
        description: err instanceof Error ? err.message : 'Please try again.',
      });
    } finally {
      setActionLoading(null);
    }
  }, []);

  const handleResetPassword = useCallback(async (user: UserWithRoles) => {
    try {
      setActionLoading(user.id);
      await sendPasswordResetEmail(user.id);
      toast.success('Password reset email sent', { description: `Sent to ${user.email}` });
    } catch (err) {
      toast.error('Failed to send password reset email', {
        description: err instanceof Error ? err.message : 'Please try again.',
      });
    } finally {
      setActionLoading(null);
    }
  }, []);

  const handleAssignRole = useCallback(async () => {
    if (!assignRoleDialog.user || !assignRoleDialog.roleId) return;

    try {
      setActionLoading(assignRoleDialog.user.id);
      await assignRoleToUser(assignRoleDialog.user.id, assignRoleDialog.roleId);
      toast.success('Role assigned', { description: 'Role assigned successfully.' });
      reloadUsers();
      setAssignRoleDialog({ user: null, roleId: '' });
    } catch (err) {
      toast.error('Failed to assign role', {
        description: err instanceof Error ? err.message : 'Please try again.',
      });
    } finally {
      setActionLoading(null);
    }
  }, [assignRoleDialog, reloadUsers]);

  const handleInviteUsers = useCallback(
    async (values: InviteFormValues) => {
      setInviteSubmitting(true);
      try {
        const results = await inviteUsers({
          emails: values.emails,
          full_name: values.full_name || undefined,
          role_id: values.role_id || undefined,
          school_ids: values.school_ids.length ? values.school_ids : undefined,
        });
        setInviteResults(results);
        const invited = results.filter((r) => r.status === 'invited').length;
        const failed = results.length - invited;
        if (invited > 0) {
          toast.success(`${invited} invitation${invited === 1 ? '' : 's'} sent`, {
            description:
              failed > 0 ? `${failed} skipped or failed — see details.` : undefined,
          });
        } else {
          toast.error('No invitations sent', {
            description: 'See the per-email results.',
          });
        }
        reloadUsers();
      } catch (err) {
        toast.error('Failed to send invitations', {
          description: err instanceof Error ? err.message : 'Please try again.',
        });
      } finally {
        setInviteSubmitting(false);
      }
    },
    [reloadUsers],
  );

  const resetInvite = useCallback(() => setInviteResults(null), []);

  // ── Bulk selection + actions ──────────────────────────────────────────────
  const toggleSelect = useCallback((id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  const setSelection = useCallback((ids: string[]) => {
    setSelectedIds(new Set(ids));
  }, []);

  const clearSelection = useCallback(() => setSelectedIds(new Set()), []);

  const handleBulkAction = useCallback(
    async (action: BulkUserAction) => {
      const ids = Array.from(selectedIds);
      if (!ids.length) return;
      setBulkLoading(true);
      try {
        const results = await bulkUserAction(action, ids);
        setBulkResults({ action, results });
        const ok = results.filter((r) => r.ok).length;
        const failed = results.length - ok;
        const notify = ok === 0 && failed > 0 ? toast.error : toast.success;
        notify(`${ok}/${results.length} ${action.replace('-', ' ')} succeeded`, {
          description: failed > 0 ? `${failed} failed — see details.` : undefined,
        });
        clearSelection();
        reloadUsers();
      } catch (err) {
        toast.error('Bulk action failed', {
          description: err instanceof Error ? err.message : 'Please try again.',
        });
      } finally {
        setBulkLoading(false);
      }
    },
    [selectedIds, clearSelection, reloadUsers],
  );

  const handleRemoveRole = useCallback(
    async (user: UserWithRoles, roleId: string) => {
      try {
        setActionLoading(user.id);
        await removeRoleFromUser(user.id, roleId);
        toast.success('Role removed', { description: 'Role removed successfully.' });
        reloadUsers();
      } catch (err) {
        toast.error('Failed to remove role', {
          description: err instanceof Error ? err.message : 'Please try again.',
        });
      } finally {
        setActionLoading(null);
      }
    },
    [reloadUsers]
  );

  const requestAction = useCallback(
    (a: PendingUserAction) => setPendingAction(a),
    [],
  );
  const confirmPendingAction = useCallback(async () => {
    const p = pendingAction;
    if (!p) return;
    setPendingAction(null);
    if (p.kind === 'unban') await handleUnbanUser(p.user);
    else if (p.kind === 'resend') await handleResendVerification(p.user);
    else if (p.kind === 'reset') await handleResetPassword(p.user);
    else if (p.kind === 'remove-role') await handleRemoveRole(p.user, p.roleId);
  }, [
    pendingAction,
    handleUnbanUser,
    handleResendVerification,
    handleResetPassword,
    handleRemoveRole,
  ]);

  return {
    // Data
    users,
    roles,
    schools,
    loadingSchools,
    stats,
    total,
    totalPages,

    // Filters
    filters,
    searchQuery,
    activeFilters,
    hasActiveFilters,
    handleFilterChange,
    handleRemoveFilter,
    handleClearAllFilters,
    setPage,

    // Loading
    loading,
    loadingStats,
    loadingRoles,
    actionLoading,
    error,

    // Permissions
    canAssignRoles,
    canUpdateAll,
    canDeleteAll,
    hasAnyAction,
    isSuperAdmin,

    // Dialogs
    assignRoleDialog,
    setAssignRoleDialog,
    deleteDialog,
    setDeleteDialog,
    banDialog,
    setBanDialog,
    inviteOpen,
    setInviteOpen,
    inviteSubmitting,
    inviteResults,
    resetInvite,
    schoolAccessUser,
    setSchoolAccessUser,

    // Bulk selection
    selectedIds,
    toggleSelect,
    setSelection,
    clearSelection,
    bulkLoading,
    bulkResults,
    setBulkResults,
    handleBulkAction,

    // Per-row confirmation
    pendingAction,
    setPendingAction,
    requestAction,
    confirmPendingAction,

    // Actions
    handleBanUser,
    handleUnbanUser,
    handleDeleteUser,
    handleResendVerification,
    handleResetPassword,
    handleAssignRole,
    handleRemoveRole,
    handleInviteUsers,
  };
}
