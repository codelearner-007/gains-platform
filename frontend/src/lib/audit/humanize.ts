/**
 * Human-readable audit rendering — a closed registry over the backend + Next
 * action vocabulary. Turns a raw `{action, actor, target, details}` row into a
 * plain sentence ("Jane banned bob@x.com") and a severity used for icon/colour.
 *
 * Shared by the admin overview activity feed and the audit-log page so both read
 * identically. Unknown actions fall back to a generic sentence, never a raw slug.
 */

export interface AuditEntryLike {
  action: string;
  module?: string | null;
  actor_email?: string | null;
  resource_id?: string | null;
  details?: Record<string, unknown> | null;
}

export type AuditSeverity = 'create' | 'update' | 'delete' | 'neutral';

/** Best label for the thing an action targeted (email > explicit label > id). */
export function auditTargetLabel(e: AuditEntryLike): string {
  const d = e.details ?? {};
  const candidate =
    (d.email as string) ??
    (d.target_label as string) ??
    (d.name as string) ??
    (d.role_name as string) ??
    (d.school_name as string);
  if (candidate) return candidate;
  if (e.resource_id) return e.resource_id.slice(0, 8);
  return 'a record';
}

export function auditSeverity(action: string): AuditSeverity {
  if (/(deleted|delete|banned|revoked|removed)/.test(action)) return 'delete';
  if (/(created|create|invited|granted|assigned|unbanned|resent|sent|triggered)/.test(action))
    return 'create';
  if (/(updated|update|changed|reset)/.test(action)) return 'update';
  return 'neutral';
}

const TEMPLATES: Record<string, (actor: string, target: string) => string> = {
  // RBAC
  role_created: (a, t) => `${a} created role ${t}`,
  role_updated: (a, t) => `${a} updated role ${t}`,
  role_deleted: (a, t) => `${a} deleted role ${t}`,
  role_permissions_updated: (a, t) => `${a} changed permissions for role ${t}`,
  role_reordered: (a) => `${a} reordered role hierarchy`,
  permission_created: (a, t) => `${a} created permission ${t}`,
  permission_deleted: (a, t) => `${a} deleted permission ${t}`,
  // Membership
  user_role_assigned: (a, t) => `${a} assigned a role to ${t}`,
  user_role_removed: (a, t) => `${a} removed a role from ${t}`,
  user_school_granted: (a, t) => `${a} granted school access to ${t}`,
  user_school_revoked: (a, t) => `${a} revoked school access from ${t}`,
  // Schools
  school_created: (a, t) => `${a} created school ${t}`,
  school_updated: (a, t) => `${a} updated school ${t}`,
  school_logo_updated: (a, t) => `${a} updated the logo for ${t}`,
  // Ingestion
  ingestion_triggered: (a) => `${a} triggered a data ingestion`,
  // Users (Next-originated)
  user_invited: (a, t) => `${a} invited ${t}`,
  user_deleted: (a, t) => `${a} deleted ${t}`,
  user_banned: (a, t) => `${a} banned ${t}`,
  user_unbanned: (a, t) => `${a} unbanned ${t}`,
  password_reset_sent: (a, t) => `${a} sent a password reset to ${t}`,
  verification_email_resent: (a, t) => `${a} resent a verification email to ${t}`,
  invitation_resent: (a, t) => `${a} resent an invitation to ${t}`,
  password_changed: (a) => `${a} changed their password`,
};

export function humanizeAudit(e: AuditEntryLike): string {
  const actor = e.actor_email || 'Someone';
  const target = auditTargetLabel(e);
  const tmpl = TEMPLATES[e.action];
  if (tmpl) return tmpl(actor, target);
  const readable = e.action.replace(/_/g, ' ');
  return e.module
    ? `${actor} performed "${readable}" in ${e.module}`
    : `${actor} performed "${readable}"`;
}
