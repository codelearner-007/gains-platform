'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import {
  Shield,
  Users,
  FileText,
  ArrowUpRight,
  Database,
  Key,
  Activity,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { UserClaims, getAccessibleAdminModules } from '@/lib/rbac/access';
import { useAdminClaims } from '@/components/admin/AdminClaimsContext';
import { getDashboardStats, type DashboardStats } from '@/lib/services/dashboard.service';

interface AdminHomePageProps {
  claims?: UserClaims;
}

const moduleIcons: Record<string, React.ComponentType<{ className?: string }>> = {
  rbac: Shield,
  users: Users,
  audit: FileText,
};

export default function AdminHomePage({ claims }: AdminHomePageProps) {
  const claimsFromContext = useAdminClaims();
  const effectiveClaims = claims ?? claimsFromContext;
  const accessibleModules = getAccessibleAdminModules(effectiveClaims);

  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function loadStats() {
      try {
        setLoading(true);
        setError(null);
        const data = await getDashboardStats();
        setStats(data);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load statistics');
      } finally {
        setLoading(false);
      }
    }
    loadStats();
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
    <div className="max-w-6xl mx-auto space-y-10">
      {/* Header */}
      <div className="space-y-2">
        <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
          Administration
        </p>
        <h1 className="text-3xl font-semibold tracking-tight text-foreground">
          Admin overview
        </h1>
        <p className="text-sm text-muted-foreground max-w-2xl">
          Monitor system health and manage access control from a single place.
        </p>
      </div>

      {/* System statistics */}
      <section className="space-y-4">
        <div className="flex items-baseline justify-between">
          <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
            System statistics
          </p>
          {!loading && !error && stats && (
            <p className="text-xs text-muted-foreground">
              {stats.recent_activity_24h} events in the last 24h
            </p>
          )}
        </div>

        {loading ? (
          <div className="grid gap-3 grid-cols-2 md:grid-cols-3 xl:grid-cols-5">
            {Array.from({ length: 5 }).map((_, i) => (
              <div key={i} className="h-24 rounded-xl bg-muted animate-pulse" />
            ))}
          </div>
        ) : error ? (
          <div className="rounded-xl border border-destructive/40 bg-destructive/5 p-4 text-sm text-destructive">
            {error}
          </div>
        ) : stats ? (
          <div className="grid gap-3 grid-cols-2 md:grid-cols-3 xl:grid-cols-5">
            <StatCard icon={Users} value={stats.total_users} label="Total users" />
            <StatCard icon={Shield} value={stats.total_roles} label="Active roles" />
            <StatCard icon={Key} value={stats.total_permissions} label="Permissions" />
            <StatCard icon={Database} value={stats.total_audit_logs} label="Audit logs" />
            <StatCard icon={Activity} value={stats.recent_activity_24h} label="Last 24h" highlight />
          </div>
        ) : null}
      </section>

      {/* Module access */}
      <section className="space-y-4">
        <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
          Modules
        </p>
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
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
                <div className="pt-2">
                  <Button variant="outline" size="sm" asChild className="w-full">
                    <span>Open module</span>
                  </Button>
                </div>
              </Link>
            );
          })}
        </div>
      </section>
    </div>
  );
}

function StatCard({
  icon: Icon,
  value,
  label,
  highlight = false,
}: {
  icon: React.ComponentType<{ className?: string }>;
  value: string | number;
  label: string;
  highlight?: boolean;
}) {
  return (
    <div className="rounded-xl border border-border bg-card p-4 flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <div
          className={`h-7 w-7 rounded-md flex items-center justify-center ${
            highlight ? 'bg-gradient-to-br from-primary to-primary/70 text-primary-foreground' : 'bg-muted text-muted-foreground'
          }`}
        >
          <Icon className="h-3.5 w-3.5" />
        </div>
      </div>
      <div className="space-y-0.5">
        <p className="text-2xl font-semibold text-foreground tracking-tight tabular-nums">{value}</p>
        <p className="text-xs text-muted-foreground">{label}</p>
      </div>
    </div>
  );
}
