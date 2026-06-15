'use client';

import { UserPlus } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useUserManagement } from './useUserManagement';
import { UserStatsCards } from './UserStatsCards';
import { UserFiltersPanel } from './UserFilters';
import { UserTable } from './UserTable';
import { UserActionDialogs } from './UserActionDialogs';
import { InviteUserDialog } from './InviteUserDialog';
import { SchoolAccessDialog } from './SchoolAccessDialog';

export default function AdminUsersPage() {
  const {
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
    schoolAccessUser,
    setSchoolAccessUser,

    // Actions
    handleBanUser,
    handleUnbanUser,
    handleDeleteUser,
    handleResendVerification,
    handleResetPassword,
    handleAssignRole,
    handleRemoveRole,
    handleInviteUser,
  } = useUserManagement();

  return (
    <div className="space-y-6 max-w-[1600px]">
      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-foreground">User Management</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Manage user accounts, roles, and permissions
          </p>
        </div>
        {canUpdateAll && (
          <Button onClick={() => setInviteOpen(true)}>
            <UserPlus className="h-4 w-4 mr-2" />
            Invite User
          </Button>
        )}
      </div>

      {/* Stats */}
      <UserStatsCards stats={stats} loading={loadingStats} />

      {/* Filters */}
      <UserFiltersPanel
        filters={filters}
        searchQuery={searchQuery}
        roles={roles}
        loadingRoles={loadingRoles}
        activeFilters={activeFilters}
        hasActiveFilters={hasActiveFilters}
        onFilterChange={handleFilterChange}
        onRemoveFilter={handleRemoveFilter}
        onClearAllFilters={handleClearAllFilters}
      />

      {/* Users Table */}
      <UserTable
        users={users}
        filters={filters}
        total={total}
        totalPages={totalPages}
        loading={loading}
        error={error}
        actionLoading={actionLoading}
        hasActiveFilters={hasActiveFilters}
        hasAnyAction={hasAnyAction}
        canAssignRoles={canAssignRoles}
        canUpdateAll={canUpdateAll}
        canDeleteAll={canDeleteAll}
        isSuperAdmin={isSuperAdmin}
        onSetPage={setPage}
        onBanUser={(user) => setBanDialog(user)}
        onUnbanUser={handleUnbanUser}
        onDeleteUser={(user) => setDeleteDialog(user)}
        onResendVerification={handleResendVerification}
        onResetPassword={handleResetPassword}
        onAssignRole={(user) => setAssignRoleDialog({ user, roleId: '' })}
        onRemoveRole={handleRemoveRole}
        onManageSchools={(user) => setSchoolAccessUser(user)}
      />

      {/* Action Dialogs */}
      <UserActionDialogs
        assignRoleDialog={assignRoleDialog}
        onAssignRoleDialogChange={setAssignRoleDialog}
        onAssignRole={handleAssignRole}
        roles={roles}
        banDialog={banDialog}
        onBanDialogChange={setBanDialog}
        onBanUser={handleBanUser}
        deleteDialog={deleteDialog}
        onDeleteDialogChange={setDeleteDialog}
        onDeleteUser={handleDeleteUser}
        actionLoading={actionLoading}
      />

      {/* Invite User */}
      <InviteUserDialog
        open={inviteOpen}
        onOpenChange={setInviteOpen}
        roles={roles}
        schools={schools}
        loadingSchools={loadingSchools}
        submitting={inviteSubmitting}
        onSubmit={handleInviteUser}
      />

      {/* Per-school membership management */}
      <SchoolAccessDialog
        user={schoolAccessUser}
        schools={schools}
        loadingSchools={loadingSchools}
        onOpenChange={(open) => !open && setSchoolAccessUser(null)}
      />
    </div>
  );
}
