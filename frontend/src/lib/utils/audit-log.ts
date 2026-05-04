import type { NextRequest } from 'next/server';
import { createServerAdminClient } from '@/lib/supabase/serverAdminClient';
import type { Json } from '@/lib/types/database.types';

interface AuditLogEntry {
  /** Caller (actor) — typically the admin performing the action. */
  actorUserId: string | null;
  /** High-level area, e.g. 'users', 'auth'. */
  module: string;
  /** Specific verb, e.g. 'user_banned', 'password_reset_sent'. */
  action: string;
  /** Optional resource identifier the action targets (target user id, etc.). */
  resourceId?: string | null;
  /** Optional structured payload (must be JSON-serializable). */
  details?: Json | null;
}

function clientIp(request: NextRequest | Request): string | null {
  const fwd = request.headers.get('x-forwarded-for');
  if (fwd) {
    const first = fwd.split(',')[0]?.trim();
    if (first) return first;
  }
  return request.headers.get('x-real-ip')?.trim() || null;
}

/**
 * Persist a tamper-resistant audit log entry. Uses the service-role Supabase
 * client because the `audit_logs` table is locked down to service_role inserts
 * only (RLS prevents tampering by authenticated users).
 *
 * Failures are logged but never thrown — audit logging must not break the
 * primary action.
 */
export async function recordAuditLog(
  request: NextRequest | Request,
  entry: AuditLogEntry,
): Promise<void> {
  try {
    const admin = await createServerAdminClient();
    const { error } = await admin.from('audit_logs').insert({
      user_id: entry.actorUserId,
      module: entry.module,
      action: entry.action,
      resource_id: entry.resourceId ?? null,
      details: entry.details ?? null,
      ip_address: clientIp(request),
      user_agent: request.headers.get('user-agent'),
    });
    if (error) {
      console.error('Audit log insert failed:', error.message);
    }
  } catch (err) {
    console.error('Audit log unexpected error:', err);
  }
}
