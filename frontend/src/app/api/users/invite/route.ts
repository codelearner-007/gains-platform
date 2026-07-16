import { NextRequest, NextResponse } from 'next/server';
import { z } from 'zod';
import { authorizeAdminRequest } from '@/lib/utils/admin-auth';
import { recordAuditLog } from '@/lib/utils/audit-log';
import { zodToApiError } from '@/lib/utils/api-errors';
import { enforceRateLimitResponse } from '@/lib/utils/rate-limit';
import { mapPool } from '@/lib/utils/concurrency';
import { serverSettings } from '@/lib/core/server-settings';
import { publicSettings } from '@/lib/core/public-settings';

export const runtime = 'nodejs';

/**
 * Superadmin user invite — supports one OR many emails (invite-only platform;
 * there is no public signup).
 *
 * Scope (architecture rule): this Next.js route only performs the Supabase
 * `auth.users` admin invite. It does NOT write application tables — role
 * assignment + per-school membership grants are a single FastAPI call
 * (`/api/v1/users/bulk/provision`) the client chains after this returns the new
 * user ids.
 *
 * Multi-email: invites run with bounded concurrency (fast — N invites ≈ a few×
 * single latency, not N×) and every email gets an independent result, so a
 * partial failure is never silent.
 *
 * Security:
 * - CSRF (`enforceSameOrigin`) + rate limit (counted once per request).
 * - Gated on `users:update_all` (existing permission — no catalog churn).
 * - NEVER returns access/refresh tokens.
 * - Errors are generic (no permission-list leak).
 */
const INVITE_CONCURRENCY = 5;
const MAX_EMAILS = 20;

const emailField = z.string().trim().toLowerCase().email('Invalid email address');

const inviteSchema = z
  .object({
    // New multi-email shape.
    emails: z.array(emailField).min(1).max(MAX_EMAILS).optional(),
    // Back-compat single-email shape.
    email: emailField.optional(),
    full_name: z.string().trim().min(1).max(120).optional(),
  })
  .refine((d) => (d.emails && d.emails.length > 0) || !!d.email, {
    message: 'Provide at least one email address.',
    path: ['emails'],
  });

type InviteStatus = 'invited' | 'already_exists' | 'failed';
interface InviteResult {
  email: string;
  status: InviteStatus;
  userId?: string | null;
  error?: string;
}

export async function POST(request: NextRequest) {
  try {
    const auth = await authorizeAdminRequest(request, 'users:update_all');
    if (auth instanceof NextResponse) return auth;

    // One rate-limit hit per request (not per email).
    const limited = await enforceRateLimitResponse({
      request,
      routeId: 'users_invite',
      policyRaw: serverSettings.FRONTEND_RATE_LIMIT_AUTH_REGISTER,
    });
    if (limited) return limited;

    let body: unknown;
    try {
      body = await request.json();
    } catch {
      return NextResponse.json({ error: 'Invalid JSON' }, { status: 400 });
    }

    const parsed = inviteSchema.safeParse(body);
    if (!parsed.success) {
      return NextResponse.json(zodToApiError(parsed.error), { status: 400 });
    }

    const { full_name } = parsed.data;
    // Normalize to a de-duplicated email list (single-email path = array of one).
    const emails = Array.from(
      new Set(parsed.data.emails ?? (parsed.data.email ? [parsed.data.email] : [])),
    );

    const redirectTo = `${publicSettings.NEXT_PUBLIC_SITE_URL}/auth/accept-invite`;

    const results = await mapPool<string, InviteResult>(
      emails,
      INVITE_CONCURRENCY,
      async (email) => {
        try {
          const { data, error } =
            await auth.adminClient.auth.admin.inviteUserByEmail(email, {
              data: full_name ? { full_name } : undefined,
              redirectTo,
            });

          if (error) {
            const exists = /already|registered|exists/i.test(error.message);
            return {
              email,
              status: exists ? 'already_exists' : 'failed',
              error: exists
                ? 'A user with this email already exists.'
                : 'Failed to send invitation.',
            };
          }

          const userId = data.user?.id ?? null;
          await recordAuditLog(request, {
            actorUserId: auth.actorUserId,
            module: 'users',
            action: 'user_invited',
            resourceId: userId,
            details: { email, full_name: full_name ?? null },
          });
          return { email, status: 'invited', userId };
        } catch {
          return { email, status: 'failed', error: 'Failed to send invitation.' };
        }
      },
    );

    // 200 even on partial failure — the client renders per-email results.
    return NextResponse.json({ results }, { status: 200 });
  } catch (error) {
    console.error('User invite error:', error);
    return NextResponse.json(
      { error: 'Failed to send invitation.' },
      { status: 500 },
    );
  }
}
