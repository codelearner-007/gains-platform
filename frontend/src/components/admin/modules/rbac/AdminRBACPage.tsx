'use client';

/**
 * Admin RBAC Page - Professional Permissions Configurator
 *
 * Two-column layout with role selection and permission matrix
 */

import { useState, useEffect } from 'react';
import { Plus, ChevronDown, ChevronUp, Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Switch } from '@/components/ui/switch';
import { Badge } from '@/components/ui/badge';
import { toast } from 'sonner';
import { UserClaims, canEditAdminModule } from '@/lib/rbac/access';
import { useAdminClaims } from '@/components/admin/AdminClaimsContext';
import { RoleCreateDialog } from './RoleCreateDialog';
import { RoleEditDialog } from './RoleEditDialog';
import { RoleDeleteDialog } from './RoleDeleteDialog';
import {
  listRoles,
  listPermissionsGrouped,
  getRolePermissions,
  updateRolePermissions,
  type RoleResponse,
  type PermissionsGroupedByModule,
} from '@/lib/services/rbac.service';

interface AdminRBACPageProps {
  claims?: UserClaims;
}

export default function AdminRBACPage({ claims }: AdminRBACPageProps) {
  const claimsFromContext = useAdminClaims();
  const effectiveClaims = claims ?? claimsFromContext;

  const [roles, setRoles] = useState<RoleResponse[]>([]);
  const [permissionsByModule, setPermissionsByModule] = useState<PermissionsGroupedByModule[]>([]);
  const [selectedRoleId, setSelectedRoleId] = useState<string | null>(null);
  const [originalPermissionIds, setOriginalPermissionIds] = useState<Set<string>>(new Set());
  const [draftPermissionIds, setDraftPermissionIds] = useState<Set<string>>(new Set());
  const [expandedModules, setExpandedModules] = useState<Set<string>>(new Set());
  const [createDialogOpen, setCreateDialogOpen] = useState(false);

  const [loadingRoles, setLoadingRoles] = useState(true);
  const [loadingPermissions, setLoadingPermissions] = useState(true);
  const [loadingRolePerms, setLoadingRolePerms] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const canEdit = canEditAdminModule(effectiveClaims, 'rbac');
  const userHierarchy = effectiveClaims?.hierarchy_level ?? 0;

  const loadData = async () => {
    try {
      setLoadingRoles(true);
      setLoadingPermissions(true);
      setError(null);

      const [rolesData, permsData] = await Promise.all([
        listRoles(),
        listPermissionsGrouped(),
      ]);

      const sortedRoles = [...rolesData].sort((a, b) => {
        if (a.hierarchy_level !== b.hierarchy_level) {
          return b.hierarchy_level - a.hierarchy_level;
        }
        return a.name.localeCompare(b.name);
      });

      setRoles(sortedRoles);
      setPermissionsByModule(permsData);
      setSelectedRoleId((prev) => prev ?? sortedRoles[0]?.id ?? null);
      setExpandedModules(new Set(permsData.map(m => m.module)));
    } catch (err) {
      console.error('Error loading RBAC data:', err);
      setError(err instanceof Error ? err.message : 'Failed to load data');
      toast('Failed to load roles and permissions', { description: 'Please try again.' });
    } finally {
      setLoadingRoles(false);
      setLoadingPermissions(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  useEffect(() => {
    if (!selectedRoleId) return;
    const roleId = selectedRoleId;

    async function loadRolePermissions() {
      try {
        setLoadingRolePerms(true);
        const permissions = await getRolePermissions(roleId);
        const permIds = new Set(permissions.map(p => p.id));
        setOriginalPermissionIds(permIds);
        setDraftPermissionIds(new Set(permIds));
      } catch (err) {
        console.error('Error loading role permissions:', err);
        toast('Failed to load role permissions', { description: 'Please try again.' });
      } finally {
        setLoadingRolePerms(false);
      }
    }

    loadRolePermissions();
  }, [selectedRoleId]);

  const hasChanges =
    originalPermissionIds.size !== draftPermissionIds.size ||
    Array.from(originalPermissionIds).some(id => !draftPermissionIds.has(id)) ||
    Array.from(draftPermissionIds).some(id => !originalPermissionIds.has(id));

  const togglePermission = (permissionId: string) => {
    if (!canEditSelectedRole) return;
    setDraftPermissionIds(prev => {
      const next = new Set(prev);
      if (next.has(permissionId)) next.delete(permissionId);
      else next.add(permissionId);
      return next;
    });
  };

  const toggleModule = (module: PermissionsGroupedByModule) => {
    if (!canEditSelectedRole) return;
    const modulePermIds = module.permissions.map(p => p.id);
    setDraftPermissionIds(prev => {
      const next = new Set(prev);
      const allSelected = modulePermIds.every(id => next.has(id));
      if (allSelected) modulePermIds.forEach(id => next.delete(id));
      else modulePermIds.forEach(id => next.add(id));
      return next;
    });
  };

  const toggleModuleExpansion = (moduleName: string) => {
    setExpandedModules(prev => {
      const next = new Set(prev);
      if (next.has(moduleName)) next.delete(moduleName);
      else next.add(moduleName);
      return next;
    });
  };

  const handleSave = async () => {
    if (!selectedRoleId || !canEdit) return;

    try {
      setSaving(true);
      await updateRolePermissions(selectedRoleId, Array.from(draftPermissionIds));
      setOriginalPermissionIds(new Set(draftPermissionIds));
      toast('Saved', { description: 'Role permissions updated successfully.' });
    } catch (err) {
      console.error('Error saving role permissions:', err);
      toast('Failed to save', {
        description: err instanceof Error ? err.message : 'Please try again.',
      });
    } finally {
      setSaving(false);
    }
  };

  const handleReset = () => {
    setDraftPermissionIds(new Set(originalPermissionIds));
  };

  const selectedRole = roles.find(r => r.id === selectedRoleId);
  const isSuperAdminRole = selectedRole?.name === 'super_admin';
  const isAboveMyHierarchy =
    typeof selectedRole?.hierarchy_level === 'number' &&
    selectedRole.hierarchy_level > userHierarchy;

  const canEditSelectedRole = canEdit && !isSuperAdminRole && !isAboveMyHierarchy;

  if (error) {
    return (
      <div className="flex items-center justify-center h-96">
        <div className="text-center space-y-2">
          <p className="text-destructive font-medium">Failed to load</p>
          <p className="text-sm text-muted-foreground">{error}</p>
          <Button onClick={loadData} variant="outline" size="sm">
            Try Again
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col max-w-[1600px]">
      {/* Header */}
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-2xl font-bold text-foreground">Permissions Configurator</h1>
          <p className="text-sm text-muted-foreground mt-1">Configure role-based access control permissions</p>
        </div>
        <div className="flex items-center gap-3">
          <Button
            variant="outline"
            onClick={handleReset}
            disabled={!hasChanges || saving || !canEditSelectedRole}
            className="shadow-sm"
          >
            Reset Defaults
          </Button>
          <Button
            onClick={handleSave}
            disabled={!hasChanges || saving || !canEditSelectedRole}
            className="shadow-sm"
          >
            {saving && <Loader2 className="h-4 w-4 animate-spin" />}
            Save Changes
          </Button>
        </div>
      </div>

      {/* Two-Column Layout */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8 flex-1">
        {/* Left Column - Role Selection */}
        <div className="lg:col-span-1 space-y-5">
          <div className="flex items-center justify-between">
            <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
              Select Role
            </h3>
            {canEdit && (
              <Button
                variant="ghost"
                size="icon"
                className="h-8 w-8 hover:bg-primary/10 hover:text-primary"
                onClick={() => setCreateDialogOpen(true)}
              >
                <Plus className="h-4 w-4" />
              </Button>
            )}
          </div>

          <div className="space-y-3">
            {loadingRoles ? (
              Array.from({ length: 3 }).map((_, i) => (
                <div key={i} className="h-24 rounded-lg bg-muted animate-pulse" />
              ))
            ) : (
              roles.map((role) => {
                const isSelected = role.id === selectedRoleId;
                const isSystemRole = role.name === 'super_admin' || role.name === 'user';
                const isDefault = role.name === 'user';
                const isAboveHierarchy = role.hierarchy_level > userHierarchy;

                const getDisabledReason = () => {
                  if (!canEdit) {
                    return 'You do not have permission to edit roles';
                  }
                  if (isAboveHierarchy) {
                    return `Cannot modify roles above your hierarchy level (${userHierarchy})`;
                  }
                  return undefined;
                };

                return (
                  <div
                    key={role.id}
                    className={`p-4 rounded-lg border-2 transition-all cursor-pointer ${
                      isSelected
                        ? 'border-primary bg-primary/5 shadow-sm'
                        : 'border-border bg-card hover:border-primary/30'
                    }`}
                    onClick={() => setSelectedRoleId(role.id)}
                  >
                    <div className="flex items-start justify-between gap-3 mb-3">
                      <div className="flex-1 min-w-0">
                        <h4 className="font-semibold text-base text-foreground truncate">{role.name}</h4>
                      </div>
                      <div className="flex items-center gap-1.5 flex-shrink-0">
                        <Badge
                          variant={isSelected ? "default" : "secondary"}
                          className="rounded-full px-2.5 font-medium"
                        >
                          {role.hierarchy_level}
                        </Badge>
                        <div onClick={(e) => e.stopPropagation()} className="flex items-center gap-0.5">
                          <RoleEditDialog
                            role={role}
                            onSuccess={loadData}
                            disabled={!canEdit || isAboveHierarchy}
                            disabledReason={getDisabledReason()}
                          />
                          <RoleDeleteDialog
                            role={role}
                            onSuccess={loadData}
                            disabled={!canEdit || isAboveHierarchy}
                            disabledReason={getDisabledReason()}
                          />
                        </div>
                      </div>
                    </div>

                    {(isSystemRole || isDefault) && (
                      <div className="flex items-center gap-2 mb-2">
                        {isSystemRole && (
                          <Badge className="text-[10px] uppercase font-semibold bg-primary/10 text-primary border-primary/20">
                            SYSTEM
                          </Badge>
                        )}
                        {isDefault && (
                          <Badge className="text-[10px] uppercase font-semibold bg-muted text-muted-foreground border-muted-foreground/20">
                            DEFAULT
                          </Badge>
                        )}
                      </div>
                    )}

                    {role.description && (
                      <p className="text-sm text-muted-foreground line-clamp-2 leading-relaxed">
                        {role.description}
                      </p>
                    )}
                  </div>
                );
              })
            )}
          </div>
        </div>

        {/* Right Column - Permissions Configuration */}
        <div className="lg:col-span-2 bg-card rounded-lg border border-border shadow-sm">
          <div className="p-6 border-b border-border bg-muted/20">
            <div className="flex items-start justify-between">
              <div>
                <h2 className="text-xl font-bold text-foreground mb-2">
                  Role: <span className="text-primary">{selectedRole?.name || 'Select a role'}</span>
                </h2>
                <p className="text-sm text-muted-foreground">
                  Configure the permission matrix for this role.
                </p>
              </div>
              {isSuperAdminRole && (
                <Badge className="bg-amber-500/10 text-amber-700 dark:text-amber-400 border-amber-500/20 font-medium">
                  Read-Only System Role
                </Badge>
              )}
            </div>
          </div>

          <div className="p-6 space-y-5 max-h-[calc(100vh-320px)] overflow-y-auto">
            {loadingPermissions || loadingRolePerms ? (
              Array.from({ length: 4 }).map((_, i) => (
                <div key={i} className="h-16 rounded-lg bg-muted animate-pulse" />
              ))
            ) : (
              permissionsByModule.map((module) => {
                const isExpanded = expandedModules.has(module.module);
                const modulePermIds = module.permissions.map(p => p.id);
                const allSelected = modulePermIds.every(id => draftPermissionIds.has(id));

                return (
                  <div key={module.module} className="border border-border rounded-lg overflow-hidden bg-card shadow-sm">
                    <div className="w-full flex items-center justify-between p-4 bg-muted/40 border-b border-border">
                      <Button
                        variant="ghost"
                        onClick={() => toggleModuleExpansion(module.module)}
                        className="flex items-center gap-3 hover:opacity-70 transition-opacity h-auto p-0"
                      >
                        {isExpanded ? (
                          <ChevronUp className="h-5 w-5 text-muted-foreground" />
                        ) : (
                          <ChevronDown className="h-5 w-5 text-muted-foreground" />
                        )}
                        <div className="text-left">
                          <h4 className="font-semibold text-base text-foreground capitalize">{module.module}</h4>
                          <p className="text-[11px] text-muted-foreground uppercase tracking-wider font-medium mt-0.5">
                            MODULE ID: {module.module.replace('_', '-').toUpperCase()}
                          </p>
                        </div>
                      </Button>

                      <div className="flex items-center gap-4">
                        <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                          Grant All
                        </span>
                        <Switch
                          checked={allSelected}
                          onCheckedChange={() => toggleModule(module)}
                          disabled={!canEditSelectedRole}
                        />
                      </div>
                    </div>

                    {isExpanded && (
                      <div className="divide-y divide-border">
                        {module.permissions.map((perm) => {
                          const checked = draftPermissionIds.has(perm.id);
                          return (
                            <div
                              key={perm.id}
                              className="flex items-center justify-between px-4 py-3.5 hover:bg-muted/30 transition-colors"
                            >
                              <div className="flex-1 pr-4">
                                <p className="font-medium text-sm text-foreground mb-1">{perm.action}</p>
                                {perm.description && (
                                  <p className="text-sm text-muted-foreground leading-relaxed">
                                    {perm.description}
                                  </p>
                                )}
                              </div>
                              <Switch
                                checked={checked}
                                onCheckedChange={() => togglePermission(perm.id)}
                                disabled={!canEditSelectedRole}
                              />
                            </div>
                          );
                        })}
                      </div>
                    )}
                  </div>
                );
              })
            )}
          </div>
        </div>
      </div>

      {/* Create Role Dialog (Controlled) */}
      {createDialogOpen && (
        <RoleCreateDialog
          open={createDialogOpen}
          onOpenChange={setCreateDialogOpen}
          onSuccess={() => {
            loadData();
            setCreateDialogOpen(false);
          }}
        />
      )}
    </div>
  );
}
