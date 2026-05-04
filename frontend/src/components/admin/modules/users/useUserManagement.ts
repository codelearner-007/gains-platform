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

function useDebounce<T>(value: T, delay: number = 300): T {
  const [debouncedValue, setDebouncedValue] = useState<T>(value);

  useEffect(() => {
    const timer = setTimeout(() => setDebouncedValue(value), delay);
    return () => clearTimeout(timer);
  }, [value, delay]);

  return debouncedValue;
}

export interface AssignRoleDialogState {
  user: UserWithRoles | null;
  roleId: string;
}

export function useUserManagement() {
  // Core data state
  const [users, setUsers] = useState<UserWithRoles[]>([]);
  const [roles, setRoles] = useState<RoleResponse[]>([]);
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
    (key: keyof UserFilters, value: string | boolean | undefined) => {
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
      toast.success('Verification email sent', { description: `Sent to ${user.email}` });
    } catch (err) {
      toast.error('Failed to send verification email', {
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

  return {
    // Data
    users,
    roles,
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

    // Actions
    handleBanUser,
    handleUnbanUser,
    handleDeleteUser,
    handleResendVerification,
    handleResetPassword,
    handleAssignRole,
    handleRemoveRole,
  };
}
