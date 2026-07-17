'use client';

/**
 * Admin RBAC Page — roles + permission matrix.
 *
 * Left column: a "seniority ladder". Order is most-senior (top) → most-junior
 * (bottom): super_admin (pinned) → custom roles → user (pinned). Custom roles
 * are drag-and-drop reorderable to set their seniority; a role senior to (or the
 * same as) the actor is locked. No hierarchy numbers are ever shown — rank is an
 * internal ordinal (lower = more senior).
 * Right column: the permission matrix for the selected role.
 */

import { useState, useEffect } from 'react';
import {
  Plus,
  ChevronDown,
  ChevronUp,
  Loader2,
  GripVertical,
  Lock,
  ShieldCheck,
  ArrowDownWideNarrow,
} from 'lucide-react';
import {
  DndContext,
  closestCenter,
  PointerSensor,
  KeyboardSensor,
  useSensor,
  useSensors,
  type DragEndEvent,
} from '@dnd-kit/core';
import {
  SortableContext,
  sortableKeyboardCoordinates,
  verticalListSortingStrategy,
  arrayMove,
  useSortable,
} from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import { Button } from '@/components/ui/button';
import { Switch } from '@/components/ui/switch';
import { Badge } from '@/components/ui/badge';
import { toast } from 'sonner';
import { cn } from '@/lib/utils';
import { UserClaims, canEditAdminModule, NO_ROLE_RANK } from '@/lib/rbac/access';
import { useAdminClaims } from '@/components/admin/AdminClaimsContext';
import { RoleCreateDialog } from './RoleCreateDialog';
import { RoleEditDialog } from './RoleEditDialog';
import { RoleDeleteDialog } from './RoleDeleteDialog';
import {
  listRoles,
  listPermissionsGrouped,
  getRolePermissions,
  updateRolePermissions,
  reorderRoles,
  type RoleResponse,
  type PermissionsGroupedByModule,
} from '@/lib/services/rbac.service';

interface AdminRBACPageProps {
  claims?: UserClaims;
}

const SYSTEM_ROLE_NAMES = new Set(['super_admin', 'user']);

// Most senior first (lowest rank first). Ties broken by name (shouldn't occur).
function sortRoles(list: RoleResponse[]): RoleResponse[] {
  return [...list].sort((a, b) =>
    a.hierarchy_rank !== b.hierarchy_rank
      ? a.hierarchy_rank - b.hierarchy_rank
      : a.name.localeCompare(b.name),
  );
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
  const [justCreatedId, setJustCreatedId] = useState<string | null>(null);

  const [loadingRoles, setLoadingRoles] = useState(true);
  const [loadingPermissions, setLoadingPermissions] = useState(true);
  const [loadingRolePerms, setLoadingRolePerms] = useState(false);
  const [saving, setSaving] = useState(false);
  const [reordering, setReordering] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const canEdit = canEditAdminModule(effectiveClaims, 'rbac');
  // Fail-closed: a missing rank claim (e.g. a stale token) reads as most-junior,
  // so the UI locks everything rather than unlocking it.
  const userRank = effectiveClaims?.hierarchy_rank ?? NO_ROLE_RANK;

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  );

  const loadData = async () => {
    try {
      setLoadingRoles(true);
      setLoadingPermissions(true);
      setError(null);
      const [rolesData, permsData] = await Promise.all([
        listRoles(),
        listPermissionsGrouped(),
      ]);
      const sortedRoles = sortRoles(rolesData);
      setRoles(sortedRoles);
      setPermissionsByModule(permsData);
      setSelectedRoleId((prev) => prev ?? sortedRoles[0]?.id ?? null);
      setExpandedModules(new Set(permsData.map((m) => m.module)));
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
        const permIds = new Set(permissions.map((p) => p.id));
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
    Array.from(originalPermissionIds).some((id) => !draftPermissionIds.has(id)) ||
    Array.from(draftPermissionIds).some((id) => !originalPermissionIds.has(id));

  const togglePermission = (permissionId: string) => {
    if (!canEditSelectedRole) return;
    setDraftPermissionIds((prev) => {
      const next = new Set(prev);
      if (next.has(permissionId)) next.delete(permissionId);
      else next.add(permissionId);
      return next;
    });
  };

  const toggleModule = (module: PermissionsGroupedByModule) => {
    if (!canEditSelectedRole) return;
    const modulePermIds = module.permissions.map((p) => p.id);
    setDraftPermissionIds((prev) => {
      const next = new Set(prev);
      const allSelected = modulePermIds.every((id) => next.has(id));
      if (allSelected) modulePermIds.forEach((id) => next.delete(id));
      else modulePermIds.forEach((id) => next.add(id));
      return next;
    });
  };

  const toggleModuleExpansion = (moduleName: string) => {
    setExpandedModules((prev) => {
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

  const handleReset = () => setDraftPermissionIds(new Set(originalPermissionIds));

  // ── Seniority ladder ────────────────────────────────────────────────────────
  const superAdminRole = roles.find((r) => r.name === 'super_admin');
  const userRole = roles.find((r) => r.name === 'user');
  const customRoles = roles.filter((r) => !SYSTEM_ROLE_NAMES.has(r.name));
  // Locked seniors (rank <= actor) are the contiguous prefix; the actor may only
  // drag the strictly-junior suffix.
  const lockedSeniors = customRoles.filter((r) => r.hierarchy_rank <= userRank);
  const manageable = customRoles.filter((r) => r.hierarchy_rank > userRank);
  const canDragAny = canEdit && manageable.length > 0;

  const handleDragEnd = async (event: DragEndEvent) => {
    const { active, over } = event;
    if (!over || active.id === over.id) return;
    const oldIndex = manageable.findIndex((r) => r.id === active.id);
    const newIndex = manageable.findIndex((r) => r.id === over.id);
    if (oldIndex < 0 || newIndex < 0) return;

    const newManageable = arrayMove(manageable, oldIndex, newIndex);
    // Optimistic reorder (server recomputes exact ranks).
    setRoles([
      ...(superAdminRole ? [superAdminRole] : []),
      ...lockedSeniors,
      ...newManageable,
      ...(userRole ? [userRole] : []),
    ]);
    setReordering(true);
    try {
      const updated = await reorderRoles(newManageable.map((r) => r.id));
      setRoles(sortRoles(updated));
      toast.success('Role seniority updated');
    } catch (err) {
      toast.error('Failed to reorder roles', {
        description: err instanceof Error ? err.message : 'Please try again.',
      });
      loadData();
    } finally {
      setReordering(false);
    }
  };

  const selectedRole = roles.find((r) => r.id === selectedRoleId);
  const isSuperAdminRole = selectedRole?.name === 'super_admin';
  // Peer-or-senior roles are not editable (strict predicate, mirrors the backend).
  const isSeniorOrPeer =
    typeof selectedRole?.hierarchy_rank === 'number' &&
    selectedRole.hierarchy_rank <= userRank;
  const canEditSelectedRole = canEdit && !isSuperAdminRole && !isSeniorOrPeer;

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

  const roleCardProps = (role: RoleResponse) => ({
    role,
    isSelected: role.id === selectedRoleId,
    canEdit,
    isSeniorOrPeer: role.hierarchy_rank <= userRank,
    justCreated: role.id === justCreatedId,
    onSelect: () => setSelectedRoleId(role.id),
    onChanged: loadData,
  });

  return (
    <div className="h-full flex flex-col max-w-[1600px]">
      {/* Header */}
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-2xl font-bold text-foreground">Roles &amp; Permissions</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Drag roles to arrange seniority — a role manages the ones below it.
            Then configure each role&apos;s permissions.
          </p>
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
        {/* Left Column - Seniority ladder */}
        <div className="lg:col-span-1 space-y-4">
          <div className="flex items-center justify-between">
            <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
              Roles {reordering && <Loader2 className="inline h-3 w-3 animate-spin ml-1" />}
            </h3>
            {canEdit && (
              <Button
                variant="ghost"
                size="icon"
                className="h-8 w-8 hover:bg-primary/10 hover:text-primary"
                onClick={() => setCreateDialogOpen(true)}
                aria-label="Create role"
              >
                <Plus className="h-4 w-4" />
              </Button>
            )}
          </div>

          {loadingRoles ? (
            <div className="space-y-3">
              {Array.from({ length: 3 }).map((_, i) => (
                <div key={i} className="h-20 rounded-lg bg-muted animate-pulse" />
              ))}
            </div>
          ) : (
            <div className="relative">
              {/* seniority rail */}
              <div className="pointer-events-none absolute left-0 top-1 bottom-1 w-px bg-border" />
              <p className="mb-2 flex items-center gap-1.5 pl-3 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                <ShieldCheck className="h-3 w-3" /> Most authority
              </p>

              <div className="space-y-3 pl-3">
                {superAdminRole && <RoleCard {...roleCardProps(superAdminRole)} pinned />}

                {lockedSeniors.map((role) => (
                  <RoleCard key={role.id} {...roleCardProps(role)} />
                ))}

                {manageable.length > 0 &&
                  (canDragAny ? (
                    <DndContext
                      sensors={sensors}
                      collisionDetection={closestCenter}
                      onDragEnd={handleDragEnd}
                    >
                      <SortableContext
                        items={manageable.map((r) => r.id)}
                        strategy={verticalListSortingStrategy}
                      >
                        <div className="space-y-3">
                          {manageable.map((role) => (
                            <SortableRoleCard key={role.id} {...roleCardProps(role)} />
                          ))}
                        </div>
                      </SortableContext>
                    </DndContext>
                  ) : (
                    manageable.map((role) => (
                      <RoleCard key={role.id} {...roleCardProps(role)} />
                    ))
                  ))}

                {customRoles.length === 0 && (
                  <div className="rounded-lg border border-dashed border-border bg-muted/20 p-4 text-center">
                    <p className="text-sm text-muted-foreground">No custom roles yet.</p>
                    <p className="text-xs text-muted-foreground mt-0.5">
                      New roles appear here, between Super admin and User.
                    </p>
                  </div>
                )}

                {userRole && <RoleCard {...roleCardProps(userRole)} pinned />}
              </div>

              <p className="mt-2 flex items-center gap-1.5 pl-3 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                <ArrowDownWideNarrow className="h-3 w-3" /> Least authority
              </p>

              {canDragAny && manageable.length === 1 && (
                <p className="mt-2 pl-3 text-xs text-muted-foreground">
                  Drag the handle to arrange seniority. Roles higher in the list
                  manage the ones below them.
                </p>
              )}
            </div>
          )}
        </div>

        {/* Right Column - Permissions */}
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
                <Badge className="bg-warning/15 text-warning border-warning/30 font-medium">
                  Read-only system role
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
                const modulePermIds = module.permissions.map((p) => p.id);
                const allSelected = modulePermIds.every((id) => draftPermissionIds.has(id));

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
                            {module.permissions.length} permission{module.permissions.length === 1 ? '' : 's'}
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
                        {module.permissions.map((perm) => (
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
                              checked={draftPermissionIds.has(perm.id)}
                              onCheckedChange={() => togglePermission(perm.id)}
                              disabled={!canEditSelectedRole}
                            />
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                );
              })
            )}
          </div>
        </div>
      </div>

      {createDialogOpen && (
        <RoleCreateDialog
          open={createDialogOpen}
          onOpenChange={setCreateDialogOpen}
          onSuccess={async (createdId?: string) => {
            await loadData();
            setCreateDialogOpen(false);
            if (createdId) {
              setJustCreatedId(createdId);
              setTimeout(() => setJustCreatedId(null), 2000);
            }
          }}
        />
      )}
    </div>
  );
}

// ── Role card ────────────────────────────────────────────────────────────────
interface RoleCardProps {
  role: RoleResponse;
  isSelected: boolean;
  canEdit: boolean;
  isSeniorOrPeer: boolean;
  justCreated?: boolean;
  onSelect: () => void;
  onChanged: () => void;
  pinned?: boolean;
  dragHandle?: React.ReactNode;
  setNodeRef?: (el: HTMLElement | null) => void;
  style?: React.CSSProperties;
}

function RoleCard({
  role,
  isSelected,
  canEdit,
  isSeniorOrPeer,
  justCreated,
  onSelect,
  onChanged,
  pinned,
  dragHandle,
  setNodeRef,
  style,
}: RoleCardProps) {
  const isSystemRole = SYSTEM_ROLE_NAMES.has(role.name);
  const isDefault = role.name === 'user';

  const disabledReason = !canEdit
    ? 'You do not have permission to edit roles'
    : isSeniorOrPeer
      ? 'This role is senior to (or the same as) yours'
      : undefined;

  return (
    <div
      ref={setNodeRef}
      style={style}
      className={cn(
        'flex items-stretch gap-1 rounded-lg border-2 transition-all',
        isSelected
          ? 'border-primary bg-primary/5 shadow-sm'
          : 'border-border bg-card hover:border-primary/30',
        pinned && 'bg-muted/30',
        justCreated && 'ring-2 ring-primary animate-in fade-in',
      )}
    >
      {/* Drag handle / lock rail */}
      <div className="flex items-center pl-1.5">
        {dragHandle ?? (
          <span
            className="flex h-6 w-6 items-center justify-center text-muted-foreground/40"
            title={isSeniorOrPeer && !isSystemRole ? 'Senior to your role — you can’t move it' : undefined}
          >
            {isSystemRole || isSeniorOrPeer ? <Lock className="h-3.5 w-3.5" /> : null}
          </span>
        )}
      </div>

      <div
        className="flex-1 min-w-0 cursor-pointer p-4 pl-1"
        onClick={onSelect}
        role="button"
        tabIndex={0}
        onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && onSelect()}
      >
        <div className="flex items-start justify-between gap-3 mb-2">
          <h4 className="font-semibold text-base text-foreground truncate">{role.name}</h4>
          <div
            onClick={(e) => e.stopPropagation()}
            className="flex items-center gap-0.5 flex-shrink-0"
          >
            <RoleEditDialog
              role={role}
              onSuccess={onChanged}
              disabled={!canEdit || isSeniorOrPeer}
              disabledReason={disabledReason}
            />
            <RoleDeleteDialog
              role={role}
              onSuccess={onChanged}
              disabled={!canEdit || isSeniorOrPeer}
              disabledReason={disabledReason}
            />
          </div>
        </div>

        {(isSystemRole || isDefault) && (
          <div className="flex items-center gap-2 mb-2">
            {isSystemRole && (
              <Badge className="text-[10px] uppercase font-semibold bg-primary/10 text-primary border-primary/20">
                System
              </Badge>
            )}
            {isDefault && (
              <Badge className="text-[10px] uppercase font-semibold bg-muted text-muted-foreground border-muted-foreground/20">
                Default
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
    </div>
  );
}

function SortableRoleCard(
  props: Omit<RoleCardProps, 'pinned' | 'dragHandle' | 'setNodeRef' | 'style'>,
) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } =
    useSortable({ id: props.role.id });
  const style: React.CSSProperties = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.6 : 1,
    zIndex: isDragging ? 20 : undefined,
  };
  const handle = (
    <button
      type="button"
      className="flex h-6 w-6 cursor-grab items-center justify-center rounded text-muted-foreground/60 hover:text-foreground active:cursor-grabbing"
      aria-label={`Drag to reorder ${props.role.name}`}
      {...attributes}
      {...listeners}
    >
      <GripVertical className="h-4 w-4" />
    </button>
  );
  return <RoleCard {...props} setNodeRef={setNodeRef} style={style} dragHandle={handle} />;
}
