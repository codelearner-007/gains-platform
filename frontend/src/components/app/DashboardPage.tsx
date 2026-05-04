'use client';

import Link from 'next/link';
import { ArrowUpRight, Settings, Shield, User, Sparkles, Code2 } from 'lucide-react';
import { useGlobal } from '@/lib/context/GlobalContext';
import { canSeeAdminEntry } from '@/lib/rbac/access';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';

export function DashboardPage() {
  const { loading, user } = useGlobal();

  const userName = user?.email?.split('@')[0] || 'User';
  const showAdmin = user && canSeeAdminEntry({
    permissions: user.app_metadata?.permissions ?? [],
    hierarchy_level: user.app_metadata?.hierarchy_level,
    user_role: user.app_metadata?.user_role,
  });

  if (loading) {
    return (
      <div className="max-w-5xl mx-auto space-y-10">
        <div className="space-y-3">
          <Skeleton className="h-9 w-72" />
          <Skeleton className="h-4 w-96" />
        </div>
        <Skeleton className="h-32 rounded-xl" />
        <div className="grid gap-4 grid-cols-1 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <Skeleton key={i} className="h-44 rounded-xl" />
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-5xl mx-auto space-y-10">
      {/* Header */}
      <div className="space-y-2">
        <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
          Dashboard
        </p>
        <h1 className="text-3xl font-semibold tracking-tight text-foreground">
          Welcome back, {userName}
        </h1>
        <p className="text-sm text-muted-foreground max-w-2xl">
          Your starting point — extend this dashboard with the features that matter to your product.
        </p>
      </div>

      {/* Welcome / setup card */}
      <div className="relative overflow-hidden rounded-xl border border-border bg-card p-6 sm:p-8">
        <div className="absolute inset-0 bg-brand-glow opacity-60 pointer-events-none" />
        <div className="relative flex flex-col sm:flex-row gap-6 items-start">
          <div className="h-12 w-12 rounded-xl bg-gradient-to-br from-primary to-primary/70 text-primary-foreground flex items-center justify-center shadow-md shrink-0">
            <Sparkles className="h-5 w-5" />
          </div>
          <div className="flex-1 space-y-3">
            <div className="space-y-1">
              <h2 className="text-lg font-semibold text-foreground">
                You&apos;re all set up
              </h2>
              <p className="text-sm text-muted-foreground leading-relaxed max-w-2xl">
                This is your empty user dashboard. Start adding features by creating new routes
                under <Code label="app/app/" /> and components under <Code label="components/app/" />.
              </p>
            </div>
            <div className="flex flex-wrap gap-2 pt-2">
              <Button asChild size="sm" variant="outline">
                <Link href="/app/user-settings">
                  <Settings className="mr-2 h-3.5 w-3.5" />
                  Configure account
                </Link>
              </Button>
              {showAdmin && (
                <Button asChild size="sm">
                  <Link href="/admin">
                    <Shield className="mr-2 h-3.5 w-3.5" />
                    Open admin panel
                  </Link>
                </Button>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Quick links */}
      <div className="space-y-4">
        <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
          Quick links
        </p>
        <div className="grid gap-4 grid-cols-1 sm:grid-cols-2 lg:grid-cols-3">
          <QuickLink
            href="/app/user-settings?section=profile"
            icon={User}
            title="Your profile"
            description="Update your name, avatar, and personal details."
          />
          <QuickLink
            href="/app/user-settings?section=security"
            icon={Settings}
            title="Account settings"
            description="Change your password, configure 2FA, manage active sessions."
          />
          {showAdmin ? (
            <QuickLink
              href="/admin"
              icon={Shield}
              title="Admin panel"
              description="Manage users, roles, permissions, and audit logs."
            />
          ) : (
            <QuickLink
              href="/app/user-settings?section=preferences"
              icon={Code2}
              title="Preferences"
              description="Theme, timezone, and display preferences."
            />
          )}
        </div>
      </div>
    </div>
  );
}

function Code({ label }: { label: string }) {
  return (
    <code className="px-1.5 py-0.5 rounded bg-muted text-[12px] font-mono text-foreground/90">
      {label}
    </code>
  );
}

function QuickLink({
  href,
  icon: Icon,
  title,
  description,
}: {
  href: string;
  icon: React.ComponentType<{ className?: string }>;
  title: string;
  description: string;
}) {
  return (
    <Link
      href={href}
      className="group relative rounded-xl border border-border bg-card p-5 card-hover flex flex-col gap-3"
    >
      <div className="flex items-center justify-between">
        <div className="h-9 w-9 rounded-md bg-primary-soft text-primary flex items-center justify-center">
          <Icon className="h-4 w-4" />
        </div>
        <ArrowUpRight className="h-4 w-4 text-muted-foreground/50 transition-colors group-hover:text-primary" />
      </div>
      <div className="space-y-1">
        <h3 className="text-sm font-semibold text-foreground">{title}</h3>
        <p className="text-xs text-muted-foreground leading-relaxed">{description}</p>
      </div>
    </Link>
  );
}
