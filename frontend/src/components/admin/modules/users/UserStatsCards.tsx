import { Users, ShieldCheck, ShieldBan, UserCheck, UserPlus } from 'lucide-react';
import { Card, CardContent } from '@/components/ui/card';
import type { UserStats } from '@/lib/services/rbac.service';

interface UserStatsCardsProps {
  stats: UserStats | null;
  loading: boolean;
}

interface StatCardProps {
  icon: React.ReactNode;
  iconBgClass: string;
  value: number;
  label: string;
}

function StatCard({ icon, iconBgClass, value, label }: StatCardProps) {
  return (
    <Card className="border-border shadow-sm hover:shadow-md transition-shadow">
      <CardContent className="pt-6">
        <div className="flex items-center justify-between mb-4">
          <div className={`p-2.5 rounded-lg ${iconBgClass}`}>{icon}</div>
          <span className="text-2xl font-bold text-foreground">{value}</span>
        </div>
        <p className="text-sm font-medium text-muted-foreground">{label}</p>
      </CardContent>
    </Card>
  );
}

function StatsLoadingSkeleton() {
  return (
    <div className="grid gap-5 md:grid-cols-2 lg:grid-cols-5">
      {Array.from({ length: 5 }).map((_, i) => (
        <div key={i} className="h-32 rounded-lg bg-muted animate-pulse" />
      ))}
    </div>
  );
}

function StatsGrid({ stats }: { stats: UserStats }) {
  return (
    <div className="grid gap-5 md:grid-cols-2 lg:grid-cols-5">
      <StatCard
        icon={<Users className="h-5 w-5 text-primary" />}
        iconBgClass="bg-primary/10"
        value={stats.total_users}
        label="Total Users"
      />
      <StatCard
        icon={<UserCheck className="h-5 w-5 text-emerald-600 dark:text-emerald-400" />}
        iconBgClass="bg-emerald-500/10"
        value={stats.active_users}
        label="Active Users"
      />
      <StatCard
        icon={<ShieldCheck className="h-5 w-5 text-sky-600 dark:text-sky-400" />}
        iconBgClass="bg-sky-500/10"
        value={stats.verified_users}
        label="Verified"
      />
      <StatCard
        icon={<ShieldBan className="h-5 w-5 text-destructive" />}
        iconBgClass="bg-destructive/10"
        value={stats.banned_users}
        label="Banned"
      />
      <StatCard
        icon={<UserPlus className="h-5 w-5 text-primary" />}
        iconBgClass="bg-primary/10"
        value={stats.new_users_30d}
        label="New (30d)"
      />
    </div>
  );
}

export function UserStatsCards({ stats, loading }: UserStatsCardsProps) {
  return (
    <div>
      <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-4">
        User Statistics
      </h3>
      {loading && <StatsLoadingSkeleton />}
      {!loading && stats && <StatsGrid stats={stats} />}
    </div>
  );
}
