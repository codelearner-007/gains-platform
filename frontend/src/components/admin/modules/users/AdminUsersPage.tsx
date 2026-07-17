'use client';

import { UserPlus } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useUserManagement, type PendingUserAction } from './useUserManagement';
import { ConfirmActionDialog } from '@/components/admin/ConfirmActionDialog';
import { UserStatsCards } from './UserStatsCards';
import { UserFiltersPanel } from './UserFilters';
import { UserTable } from './UserTable';
import { UserActionDialogs } from './UserActionDialogs';
import { InviteUserDialog } from './InviteUserDialog';
import { SchoolAccessDialog } from './SchoolAccessDialog';
import { BulkActionBar } from './BulkActionBar';
import { ResultsDialog } from './ResultsDialog';

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
    handleDeleteUser,
    handleAssignRole,
    handleInviteUsers,
  } = useUserManagement();

  const bulkEnabled = canUpdateAll || canDeleteAll;
  const emailById = new Map(users.map((u) => [u.id, u.email]));

  return (
    <div className="space-y-6 max-w-[1600px]">
      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-foreground">User Management</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Manage user accounts, roles, and school access
          </p>
        </div>
        {canUpdateAll && (
          <Button onClick={() => setInviteOpen(true)}>
            <UserPlus className="h-4 w-4 mr-2" />
            Invite users
          </Button>
        )}
      </div>

      {/* Stats */}
      <UserStatsCards stats={stats} loading={loadingStats} />

      {/* Search + filters menu + page size + chips */}
      <UserFiltersPanel
        filters={filters}
        searchQuery={searchQuery}
        roles={roles}
        schools={schools}
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
        selectable={bulkEnabled}
        selectedIds={selectedIds}
        onToggleSelect={toggleSelect}
        onSetSelection={setSelection}
        onSetPage={setPage}
        onBanUser={(user) => setBanDialog(user)}
        onUnbanUser={(user) => requestAction({ kind: 'unban', user })}
        onDeleteUser={(user) => setDeleteDialog(user)}
        onResendVerification={(user) => requestAction({ kind: 'resend', user })}
        onResetPassword={(user) => requestAction({ kind: 'reset', user })}
        onAssignRole={(user) => setAssignRoleDialog({ user, roleId: '' })}
        onRemoveRole={(user, roleId) =>
          requestAction({
            kind: 'remove-role',
            user,
            roleId,
            roleName:
              user.roles.find((r) => r.role_id === roleId)?.role.name ?? 'role',
          })
        }
        onManageSchools={(user) => setSchoolAccessUser(user)}
      />

      {/* Floating bulk action bar (only when rows are selected) */}
      {bulkEnabled && (
        <BulkActionBar
          count={selectedIds.size}
          loading={bulkLoading}
          canUpdate={canUpdateAll}
          canDelete={canDeleteAll}
          onAction={handleBulkAction}
          onClear={clearSelection}
        />
      )}

      {/* Bulk-action results */}
      {bulkResults && (
        <ResultsDialog
          open={!!bulkResults}
          onOpenChange={(o) => !o && setBulkResults(null)}
          title={`Bulk ${bulkResults.action.replace('-', ' ')} — results`}
          results={bulkResults.results.map((r) => ({
            label: emailById.get(r.user_id) ?? r.user_id.slice(0, 8),
            ok: r.ok,
            error: r.error,
          }))}
        />
      )}

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

      {/* Invite (single or multi-email) */}
      <InviteUserDialog
        open={inviteOpen}
        onOpenChange={setInviteOpen}
        roles={roles}
        schools={schools}
        loadingSchools={loadingSchools}
        submitting={inviteSubmitting}
        results={inviteResults}
        onSubmit={handleInviteUsers}
        onReset={resetInvite}
      />

      {/* Per-school membership management */}
      <SchoolAccessDialog
        user={schoolAccessUser}
        schools={schools}
        loadingSchools={loadingSchools}
        onOpenChange={(open) => !open && setSchoolAccessUser(null)}
      />

      {/* Confirmation for the per-row unban / resend / reset / remove-role actions */}
      {pendingAction && (() => {
        const copy = confirmCopy(pendingAction);
        return (
          <ConfirmActionDialog
            open={!!pendingAction}
            onOpenChange={(o) => !o && setPendingAction(null)}
            title={copy.title}
            description={copy.description}
            confirmLabel={copy.confirmLabel}
            variant={copy.variant}
            loading={actionLoading === pendingAction.user.id}
            onConfirm={confirmPendingAction}
          />
        );
      })()}
    </div>
  );
}

function confirmCopy(a: PendingUserAction): {
  title: string;
  description: React.ReactNode;
  confirmLabel: string;
  variant: 'default' | 'destructive';
} {
  const email = <span className="font-semibold text-foreground">{a.user.email}</span>;
  switch (a.kind) {
    case 'unban':
      return {
        title: 'Unban user?',
        description: <>Allow {email} to sign in again.</>,
        confirmLabel: 'Unban',
        variant: 'default',
      };
    case 'resend':
      return {
        title: 'Resend invitation?',
        description: <>Send a fresh invitation email to {email}.</>,
        confirmLabel: 'Resend',
        variant: 'default',
      };
    case 'reset':
      return {
        title: 'Send password reset?',
        description: <>Email a password-reset link to {email}.</>,
        confirmLabel: 'Send reset',
        variant: 'default',
      };
    case 'remove-role':
      return {
        title: 'Remove role?',
        description: (
          <>
            Remove{' '}
            <span className="font-semibold text-foreground">{a.roleName}</span> from{' '}
            {email}. They lose that role&apos;s permissions on their next sign-in.
          </>
        ),
        confirmLabel: 'Remove role',
        variant: 'destructive',
      };
  }
}
