'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { format } from 'date-fns';
import { toast } from 'sonner';
import {
  Shield,
  Users,
  FileText,
  ArrowUpRight,
  UserPlus,
  Building2,
  MailWarning,
  Send,
  Activity,
  Database,
  CheckCircle2,
  AlertTriangle,
  Ban,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { UserClaims, getAccessibleAdminModules } from '@/lib/rbac/access';
import { useAdminClaims } from '@/components/admin/AdminClaimsContext';
import { hasPermission } from '@/lib/utils/rbac';
import { resendVerificationEmail } from '@/lib/services/rbac.service';
import {
  getAdminOverview,
  type AdminOverview,
  type PendingInvite,
  type SchoolCoverage,
  type ActivityEntry,
} from '@/lib/services/dashboard.service';
import {
  humanizeAudit,
  auditSeverity,
  type AuditSeverity,
} from '@/lib/audit/humanize';

interface AdminHomePageProps {
  claims?: UserClaims;
}

const moduleIcons: Record<string, React.ComponentType<{ className?: string }>> = {
  rbac: Shield,
  users: Users,
  audit: FileText,
  schools: Building2,
};

export default function AdminHomePage({ claims }: AdminHomePageProps) {
  const claimsFromContext = useAdminClaims();
  const effectiveClaims = claims ?? claimsFromContext;
  const accessibleModules = getAccessibleAdminModules(effectiveClaims);
  const perms = effectiveClaims?.permissions ?? [];

  const [data, setData] = useState<AdminOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function load() {
      try {
        setLoading(true);
        setError(null);
        setData(await getAdminOverview());
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load overview');
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  if (accessibleModules.length === 0) {
    return (
      <div className="max-w-3xl mx-auto py-16 text-center space-y-3">
        <div className="mx-auto h-12 w-12 rounded-xl bg-muted flex items-center justify-center">
          <Shield className="h-5 w-5 text-muted-foreground" />
        </div>
        <h1 className="text-xl font-semibold text-foreground">No admin modules available</h1>
        <p className="text-sm text-muted-foreground">
          Contact your administrator if you believe you should have access.
        </p>
      </div>
    );
  }

  return (
    <div className="max-w-6xl mx-auto space-y-8">
      {/* Header + quick actions */}
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div className="space-y-1.5">
          <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
            Administration
          </p>
          <h1 className="text-3xl font-semibold tracking-tight text-foreground">
            Admin overview
          </h1>
          <p className="text-sm text-muted-foreground">
            People, access, and per-school data coverage at a glance.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          {hasPermission(perms, 'users:update_all') && (
            <Button asChild variant="outline" size="sm">
              <Link href="/admin/users">
                <UserPlus className="h-4 w-4 mr-2" /> Invite users
              </Link>
            </Button>
          )}
          {hasPermission(perms, 'schools:create') && (
            <Button asChild variant="outline" size="sm">
              <Link href="/admin/schools">
                <Building2 className="h-4 w-4 mr-2" /> Add school
              </Link>
            </Button>
          )}
          {hasPermission(perms, 'roles:update') && (
            <Button asChild variant="outline" size="sm">
              <Link href="/admin/rbac">
                <Shield className="h-4 w-4 mr-2" /> Manage roles
              </Link>
            </Button>
          )}
        </div>
      </div>

      {loading ? (
        <OverviewSkeleton />
      ) : error ? (
        <div className="rounded-xl border border-destructive/40 bg-destructive/5 p-4 text-sm text-destructive">
          {error}
        </div>
      ) : data ? (
        <>
          {/* People + Access distribution */}
          <div className="grid gap-4 lg:grid-cols-3">
            <PeopleCard data={data} />
            <div className="lg:col-span-2 grid gap-4 sm:grid-cols-2">
              <DistributionCard
                title="Users by role"
                icon={Shield}
                rows={data.roles.map((r) => ({ label: r.name, value: r.users }))}
              />
              <DistributionCard
                title="Users by school"
                icon={Building2}
                rows={data.schools_users.map((s) => ({
                  label: s.short_name || s.name,
                  value: s.users,
                }))}
              />
            </div>
          </div>

          {/* Pending invites */}
          {data.pending_invites.length > 0 && (
            <PendingInvitesCard invites={data.pending_invites} />
          )}

          {/* Data coverage */}
          <CoverageCard rows={data.coverage} />

          {/* Activity + ingestion */}
          <div className="grid gap-4 lg:grid-cols-3">
            <div className="lg:col-span-2">
              <ActivityFeed entries={data.recent_activity} />
            </div>
            {hasPermission(perms, 'ingestion:read') && data.ingestion && (
              <IngestionStrip ingestion={data.ingestion} />
            )}
          </div>
        </>
      ) : null}

      {/* Module navigation */}
      <section className="space-y-4 pt-2">
        <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
          Modules
        </p>
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
          {accessibleModules.map((module) => {
            const Icon = moduleIcons[module.key] || Shield;
            return (
              <Link
                key={module.key}
                href={`/admin/${module.key}`}
                className="group relative rounded-xl border border-border bg-card p-5 card-hover flex flex-col gap-4"
              >
                <div className="flex items-center justify-between">
                  <div className="h-9 w-9 rounded-md bg-primary-soft text-primary flex items-center justify-center">
                    <Icon className="h-4 w-4" />
                  </div>
                  <ArrowUpRight className="h-4 w-4 text-muted-foreground/50 transition-colors group-hover:text-primary" />
                </div>
                <div className="space-y-1">
                  <h3 className="text-sm font-semibold text-foreground">{module.name}</h3>
                  <p className="text-xs text-muted-foreground leading-relaxed">
                    {module.description}
                  </p>
                </div>
              </Link>
            );
          })}
        </div>
      </section>
    </div>
  );
}

// ── People ──────────────────────────────────────────────────────────────────
function PeopleCard({ data }: { data: AdminOverview }) {
  const p = data.people;
  const metrics = [
    { label: 'Total users', value: p.total },
    { label: 'Active · 7d', value: p.active_7d },
    { label: 'Active · 30d', value: p.active_30d },
    { label: 'Pending', value: p.pending_invites, warn: p.pending_invites > 0 },
    { label: 'Banned', value: p.banned, danger: p.banned > 0 },
  ];
  return (
    <div className="rounded-xl border border-border bg-card p-5">
      <div className="flex items-center gap-2 mb-4">
        <Users className="h-4 w-4 text-primary" />
        <h3 className="text-sm font-semibold">People</h3>
      </div>
      <div className="grid grid-cols-2 gap-x-4 gap-y-4">
        {metrics.map((m) => (
          <div key={m.label}>
            <p
              className={`text-2xl font-semibold tabular-nums ${
                m.danger
                  ? 'text-destructive'
                  : m.warn
                    ? 'text-warning'
                    : 'text-foreground'
              }`}
            >
              {m.value}
            </p>
            <p className="text-xs text-muted-foreground">{m.label}</p>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Distribution bars ───────────────────────────────────────────────────────
function DistributionCard({
  title,
  icon: Icon,
  rows,
}: {
  title: string;
  icon: React.ComponentType<{ className?: string }>;
  rows: { label: string; value: number }[];
}) {
  const max = Math.max(1, ...rows.map((r) => r.value));
  return (
    <div className="rounded-xl border border-border bg-card p-5">
      <div className="flex items-center gap-2 mb-4">
        <Icon className="h-4 w-4 text-primary" />
        <h3 className="text-sm font-semibold">{title}</h3>
      </div>
      {rows.length === 0 ? (
        <p className="text-xs text-muted-foreground">No data</p>
      ) : (
        <div className="space-y-3">
          {rows.map((r) => (
            <div key={r.label} className="space-y-1">
              <div className="flex items-center justify-between text-xs">
                <span className="truncate text-foreground">{r.label}</span>
                <span className="tabular-nums text-muted-foreground">{r.value}</span>
              </div>
              <div className="h-1.5 rounded-full bg-muted overflow-hidden">
                <div
                  className="h-full rounded-full bg-primary"
                  style={{ width: `${(r.value / max) * 100}%` }}
                />
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ── Pending invites ─────────────────────────────────────────────────────────
function PendingInvitesCard({ invites }: { invites: PendingInvite[] }) {
  const [busy, setBusy] = useState<string | null>(null);
  const resend = async (inv: PendingInvite) => {
    setBusy(inv.id);
    try {
      await resendVerificationEmail(inv.id);
      toast.success('Invitation resent', { description: inv.email ?? undefined });
    } catch {
      toast.error('Failed to resend invitation');
    } finally {
      setBusy(null);
    }
  };
  return (
    <div className="rounded-xl border border-warning/40 bg-warning/5 p-5">
      <div className="flex items-center gap-2 mb-3">
        <MailWarning className="h-4 w-4 text-warning" />
        <h3 className="text-sm font-semibold">
          Pending invitations{' '}
          <span className="font-normal text-muted-foreground">
            ({invites.length})
          </span>
        </h3>
      </div>
      <div className="space-y-1.5">
        {invites.map((inv) => (
          <div
            key={inv.id}
            className="flex items-center justify-between gap-3 rounded-md bg-card border border-border px-3 py-2 text-sm"
          >
            <div className="min-w-0">
              <p className="truncate">{inv.email ?? inv.id.slice(0, 8)}</p>
              {inv.invited_at && (
                <p className="text-xs text-muted-foreground">
                  Invited {format(new Date(inv.invited_at), 'MMM d, yyyy')}
                </p>
              )}
            </div>
            <Button
              variant="ghost"
              size="sm"
              disabled={busy === inv.id}
              onClick={() => resend(inv)}
            >
              <Send className="h-3.5 w-3.5 mr-1.5" />
              Resend
            </Button>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Coverage table ──────────────────────────────────────────────────────────
function CoverageCard({ rows }: { rows: SchoolCoverage[] }) {
  return (
    <div className="rounded-xl border border-border bg-card">
      <div className="flex items-center gap-2 p-5 pb-3">
        <Database className="h-4 w-4 text-primary" />
        <h3 className="text-sm font-semibold">Data coverage by school</h3>
      </div>
      <div className="overflow-x-auto">
        <Table>
          <TableHeader>
            <TableRow className="bg-muted/40">
              <TableHead className="font-semibold">School</TableHead>
              <TableHead className="font-semibold text-right">Assessments</TableHead>
              <TableHead className="font-semibold text-right">Students</TableHead>
              <TableHead className="font-semibold text-right">Subjects</TableHead>
              <TableHead className="font-semibold text-right">Sessions</TableHead>
              <TableHead className="font-semibold">Data through</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.map((s) => (
              <TableRow key={s.school_id}>
                <TableCell>
                  <div className="flex items-center gap-3">
                    <SchoolAvatar name={s.name} logo={s.logo_url} />
                    <div className="min-w-0">
                      <p className="font-medium text-sm truncate">{s.name}</p>
                      {!s.is_active && (
                        <span className="text-xs text-muted-foreground">Inactive</span>
                      )}
                    </div>
                  </div>
                </TableCell>
                <TableCell className="text-right tabular-nums">{s.assessments}</TableCell>
                <TableCell className="text-right tabular-nums">{s.students}</TableCell>
                <TableCell className="text-right tabular-nums">{s.subjects}</TableCell>
                <TableCell className="text-right tabular-nums">{s.sessions_covered}</TableCell>
                <TableCell>
                  <div className="flex items-center gap-2">
                    <span className="text-sm text-muted-foreground">
                      {s.last_assessment_date
                        ? format(new Date(s.last_assessment_date), 'MMM d, yyyy')
                        : '—'}
                    </span>
                    {s.is_stale && (
                      <Badge className="bg-warning/15 text-warning border-warning/30">
                        Stale
                      </Badge>
                    )}
                  </div>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}

function SchoolAvatar({ name, logo }: { name: string; logo: string | null }) {
  const initials = name
    .split(/\s+/)
    .slice(0, 2)
    .map((w) => w[0])
    .join('')
    .toUpperCase();
  if (logo) {
    // eslint-disable-next-line @next/next/no-img-element
    return (
      <img
        src={logo}
        alt=""
        className="h-8 w-8 rounded-md object-cover border border-border"
      />
    );
  }
  return (
    <div className="flex h-8 w-8 items-center justify-center rounded-md bg-muted text-xs font-semibold text-muted-foreground">
      {initials}
    </div>
  );
}

// ── Activity feed ───────────────────────────────────────────────────────────
const SEVERITY_STYLE: Record<AuditSeverity, string> = {
  create: 'bg-success/15 text-success',
  update: 'bg-muted text-muted-foreground',
  delete: 'bg-destructive/10 text-destructive',
  neutral: 'bg-muted text-muted-foreground',
};

function severityIcon(sev: AuditSeverity) {
  if (sev === 'delete') return Ban;
  if (sev === 'create') return CheckCircle2;
  return Activity;
}

function ActivityFeed({ entries }: { entries: ActivityEntry[] }) {
  return (
    <div className="rounded-xl border border-border bg-card p-5 h-full">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <Activity className="h-4 w-4 text-primary" />
          <h3 className="text-sm font-semibold">Recent activity</h3>
        </div>
        <Link
          href="/admin/audit"
          className="text-xs text-primary hover:underline"
        >
          View all
        </Link>
      </div>
      {entries.length === 0 ? (
        <p className="text-xs text-muted-foreground">No recent activity</p>
      ) : (
        <ul className="space-y-3">
          {entries.map((e) => {
            const sev = auditSeverity(e.action);
            const Icon = severityIcon(sev);
            return (
              <li key={e.id} className="flex items-start gap-3">
                <div
                  className={`mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full ${SEVERITY_STYLE[sev]}`}
                >
                  <Icon className="h-3.5 w-3.5" />
                </div>
                <div className="min-w-0 flex-1">
                  <p className="text-sm text-foreground">{humanizeAudit(e)}</p>
                  {e.created_at && (
                    <p className="text-xs text-muted-foreground">
                      {format(new Date(e.created_at), 'MMM d, yyyy · h:mm a')}
                    </p>
                  )}
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

// ── Ingestion health ────────────────────────────────────────────────────────
function IngestionStrip({
  ingestion,
}: {
  ingestion: NonNullable<AdminOverview['ingestion']>;
}) {
  const ok = ingestion.status === 'succeeded';
  return (
    <div className="rounded-xl border border-border bg-card p-5 h-full">
      <div className="flex items-center gap-2 mb-4">
        <Database className="h-4 w-4 text-primary" />
        <h3 className="text-sm font-semibold">Ingestion health</h3>
      </div>
      <div className="flex items-center gap-2 mb-3">
        {ok ? (
          <CheckCircle2 className="h-4 w-4 text-success" />
        ) : (
          <AlertTriangle className="h-4 w-4 text-destructive" />
        )}
        <span
          className={`text-sm font-medium ${ok ? 'text-success' : 'text-destructive'}`}
        >
          {ingestion.status ?? 'unknown'}
        </span>
      </div>
      <dl className="space-y-2 text-sm">
        {ingestion.finished_at && (
          <Row
            label="Last run"
            value={format(new Date(ingestion.finished_at), 'MMM d, h:mm a')}
          />
        )}
        {ingestion.files_processed != null && (
          <Row label="Files" value={String(ingestion.files_processed)} />
        )}
        {ingestion.rows_inserted != null && (
          <Row label="Rows" value={ingestion.rows_inserted.toLocaleString()} />
        )}
        {ingestion.error_count != null && (
          <Row
            label="Errors"
            value={String(ingestion.error_count)}
            danger={ingestion.error_count > 0}
          />
        )}
      </dl>
    </div>
  );
}

function Row({
  label,
  value,
  danger,
}: {
  label: string;
  value: string;
  danger?: boolean;
}) {
  return (
    <div className="flex items-center justify-between">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className={`tabular-nums ${danger ? 'text-destructive' : 'text-foreground'}`}>
        {value}
      </dd>
    </div>
  );
}

function OverviewSkeleton() {
  return (
    <div className="space-y-4">
      <div className="grid gap-4 lg:grid-cols-3">
        {Array.from({ length: 3 }).map((_, i) => (
          <div key={i} className="h-40 rounded-xl bg-muted animate-pulse" />
        ))}
      </div>
      <div className="h-56 rounded-xl bg-muted animate-pulse" />
    </div>
  );
}
