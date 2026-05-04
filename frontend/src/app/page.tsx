import Link from 'next/link';
import type { Metadata } from 'next';
import {
  ArrowRight,
  ShieldCheck,
  KeyRound,
  Layers,
  Database,
  CheckCircle2,
  Lock,
  Zap,
  Users,
  ScrollText,
  UserPlus,
  LogIn,
  Crown,
  Sparkles,
  Code2,
  Server,
} from 'lucide-react';
import AuthAwareButtons from '@/components/common/AuthAwareButtons';
import { SiteNav } from '@/components/common/SiteNav';
import { SiteFooter } from '@/components/common/SiteFooter';
import { Button } from '@/components/ui/button';
import { publicSettings } from '@/lib/core/public-settings';

export const metadata: Metadata = {
  title: 'SaaS Starter Template — Next.js + FastAPI + Supabase',
  description:
    'A production-ready SaaS starter with authentication, RBAC, admin panel, and audit logging. Skip the boilerplate, focus on your product.',
};

export default function Home() {
  const productName = publicSettings.NEXT_PUBLIC_PRODUCTNAME;

  return (
    <div className="min-h-screen flex flex-col bg-background text-foreground selection:bg-primary/30">
      <SiteNav />
      <main className="flex-1 pt-14">
        {/* ==================== HERO ==================== */}
        <section className="relative overflow-hidden">
          <div className="absolute inset-0 bg-dotgrid opacity-50 pointer-events-none" />
          <div className="absolute inset-x-0 top-0 h-[700px] bg-brand-glow pointer-events-none" />

          <div className="relative max-w-6xl mx-auto px-6 pt-24 pb-20 lg:pt-36 lg:pb-32 text-center">
            <div className="inline-flex items-center gap-2 rounded-full border border-border bg-card/60 backdrop-blur px-3 py-1 text-xs font-medium text-foreground mb-8">
              <span className="h-1.5 w-1.5 rounded-full bg-primary animate-pulse" />
              <span className="text-muted-foreground">v1.0 — production-ready</span>
              <span className="h-3 w-px bg-border mx-1" />
              <span className="font-semibold">{productName}</span>
            </div>

            <h1 className="text-5xl sm:text-6xl lg:text-7xl font-semibold tracking-tight leading-[1.05] max-w-4xl mx-auto">
              Ship your SaaS{' '}
              <span className="text-gradient-brand">weeks faster</span>
            </h1>

            <p className="mt-6 text-base sm:text-lg text-muted-foreground max-w-2xl mx-auto leading-relaxed">
              A production-grade starter with authentication, RBAC, admin panel, and audit
              logging — already wired across Next.js, FastAPI, and Supabase. Skip the
              boilerplate, focus on what makes your product unique.
            </p>

            <div className="mt-10 flex flex-col sm:flex-row items-center justify-center gap-3">
              <AuthAwareButtons />
            </div>

            <div className="mt-12 flex flex-wrap items-center justify-center gap-x-6 gap-y-2 text-xs text-muted-foreground">
              <span className="flex items-center gap-1.5">
                <CheckCircle2 className="h-3.5 w-3.5 text-success" /> MIT licensed
              </span>
              <span className="flex items-center gap-1.5">
                <CheckCircle2 className="h-3.5 w-3.5 text-success" /> No CORS, no glue code
              </span>
              <span className="flex items-center gap-1.5">
                <CheckCircle2 className="h-3.5 w-3.5 text-success" /> Tamper-resistant audit log
              </span>
              <span className="flex items-center gap-1.5">
                <CheckCircle2 className="h-3.5 w-3.5 text-success" /> RLS + UUID v7
              </span>
            </div>
          </div>

          {/* Hero preview tile */}
          <div className="relative max-w-5xl mx-auto px-6 pb-16">
            <HeroPreview />
          </div>
        </section>

        {/* ==================== FEATURES ==================== */}
        <section id="features" className="border-t border-border/60 py-24 sm:py-32">
          <div className="max-w-6xl mx-auto px-6">
            <SectionHeading
              eyebrow="What's included"
              title="Everything you need on day one"
              subtitle="Auth, permissions, admin tooling, and audit trail — implemented, hardened, and ready to extend."
            />

            <div className="mt-14 grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-px bg-border rounded-2xl overflow-hidden border border-border">
              <FeatureCell
                icon={KeyRound}
                title="Authentication"
                description="Email/password, OAuth providers, MFA/TOTP, email verification, password reset."
              />
              <FeatureCell
                icon={ShieldCheck}
                title="Role-Based Access Control"
                description="13 permissions across 4 modules, hierarchical roles, JWT claims hook for instant checks."
              />
              <FeatureCell
                icon={Layers}
                title="Admin Panel"
                description="User management, RBAC configuration, audit log inspection — already built."
              />
              <FeatureCell
                icon={Database}
                title="Database Foundation"
                description="Supabase Postgres with RLS, UUID v7 primary keys, async SQLAlchemy, clean migrations."
              />
              <FeatureCell
                icon={ScrollText}
                title="Audit Trail"
                description="Service-role-only inserts, paginated viewer, filterable by module / action / date range."
              />
              <FeatureCell
                icon={Users}
                title="User Settings"
                description="Profile, password, MFA, theme & timezone preferences, active session management."
              />
            </div>
          </div>
        </section>

        {/* ==================== WORKFLOW / FLOW ==================== */}
        <section id="workflow" className="bg-muted/30 border-y border-border py-24 sm:py-32">
          <div className="max-w-6xl mx-auto px-6">
            <SectionHeading
              eyebrow="From signup to admin"
              title="A clean path your users will follow"
              subtitle="Every step is wired end-to-end. Just run the project."
            />

            <div className="mt-14 grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
              <FlowStep
                step="01"
                icon={UserPlus}
                title="Register"
                description="Email + password with strong password validation and email verification."
              />
              <FlowStep
                step="02"
                icon={LogIn}
                title="Sign in"
                description="MFA-aware, session-cookie based. First user becomes super_admin automatically."
              />
              <FlowStep
                step="03"
                icon={Layers}
                title="Use the app"
                description="A clean dashboard + settings shell for you to drop your features into."
              />
              <FlowStep
                step="04"
                icon={Crown}
                title="Administrate"
                description="Manage users, roles, permissions, and inspect the audit trail — RBAC-gated."
              />
            </div>
          </div>
        </section>

        {/* ==================== STACK ==================== */}
        <section id="stack" className="py-24 sm:py-32">
          <div className="max-w-6xl mx-auto px-6">
            <SectionHeading
              eyebrow="The stack"
              title="Best-in-class tools, wired together"
              subtitle="Modern, well-supported, production-tested foundations."
            />

            <div className="mt-14 grid grid-cols-2 md:grid-cols-4 gap-4 max-w-5xl mx-auto">
              <StackTile label="Next.js 16" sub="React 19, App Router" icon={Code2} />
              <StackTile label="FastAPI" sub="Python, async SQLAlchemy" icon={Server} />
              <StackTile label="Supabase" sub="Postgres, Auth, Storage" icon={Database} />
              <StackTile label="Tailwind v4" sub="shadcn/ui components" icon={Sparkles} />
            </div>
          </div>
        </section>

        {/* ==================== ARCHITECTURE ==================== */}
        <section id="architecture" className="border-y border-border bg-muted/30 py-24 sm:py-32">
          <div className="max-w-6xl mx-auto px-6">
            <SectionHeading
              eyebrow="Architecture"
              title="Clean separation of concerns"
              subtitle="Next.js handles auth & UI. FastAPI handles all data via Router → Service → Repository. No CORS — Next.js rewrites /api/v1/* to FastAPI."
            />

            <div className="mt-14 max-w-4xl mx-auto">
              <ArchitectureDiagram />
            </div>
          </div>
        </section>

        {/* ==================== SECURITY ==================== */}
        <section className="py-24 sm:py-32">
          <div className="max-w-6xl mx-auto px-6">
            <SectionHeading
              eyebrow="Security baked in"
              title="The hard parts — already done"
              subtitle="Production-grade defaults you can trust on day one."
            />

            <div className="mt-14 grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              <SecurityChip
                icon={Lock}
                title="CSRF protection"
                description="Same-origin enforcement on every mutation route."
              />
              <SecurityChip
                icon={ShieldCheck}
                title="JWKS verification"
                description="ES256 with rotation handling and concurrent-fetch lock."
              />
              <SecurityChip
                icon={KeyRound}
                title="MFA, fail-closed"
                description="Errors block by default — no silent bypass."
              />
              <SecurityChip
                icon={Crown}
                title="Superadmin protection"
                description="Live auth.admin.getUserById() — never trust stale metadata."
              />
              <SecurityChip
                icon={ScrollText}
                title="Tamper-resistant audit"
                description="RLS locks audit_logs to service_role inserts only."
              />
              <SecurityChip
                icon={Zap}
                title="Rate limiting"
                description="Redis-backed limits on login, register, password reset."
              />
            </div>
          </div>
        </section>

        {/* ==================== CTA ==================== */}
        <section className="py-24 sm:py-32 border-t border-border">
          <div className="max-w-6xl mx-auto px-6">
            <div className="relative overflow-hidden rounded-3xl border border-border bg-card p-12 sm:p-16">
              <div className="absolute inset-0 bg-brand-glow opacity-80 pointer-events-none" />
              <div className="absolute inset-0 bg-dotgrid opacity-40 pointer-events-none" />
              <div className="relative max-w-2xl mx-auto text-center space-y-6">
                <div className="inline-flex items-center gap-2 text-xs font-medium text-muted-foreground">
                  <CheckCircle2 className="h-3.5 w-3.5 text-success" />
                  <span>MIT licensed — fork and ship</span>
                </div>
                <h2 className="text-3xl sm:text-4xl font-semibold tracking-tight">
                  Start building <span className="text-gradient-brand">today</span>
                </h2>
                <p className="text-sm sm:text-base text-muted-foreground leading-relaxed">
                  Skip the auth, RBAC, and admin panel boilerplate. Clone the repo and focus on
                  what makes your product unique.
                </p>
                <div className="flex flex-col sm:flex-row items-center justify-center gap-3 pt-2">
                  <Button asChild size="xl" className="btn-glow">
                    <Link href="/auth/register">
                      Get started
                      <ArrowRight className="ml-1 h-4 w-4" />
                    </Link>
                  </Button>
                  <Button asChild size="xl" variant="outline">
                    <Link href="#features">Explore features</Link>
                  </Button>
                </div>
              </div>
            </div>
          </div>
        </section>
      </main>
      <SiteFooter />
    </div>
  );
}

/* ============================================================
   Sub-components
   ============================================================ */

function SectionHeading({
  eyebrow,
  title,
  subtitle,
}: {
  eyebrow: string;
  title: string;
  subtitle?: string;
}) {
  return (
    <div className="text-center max-w-2xl mx-auto space-y-3">
      <p className="text-xs font-medium uppercase tracking-wider text-primary">{eyebrow}</p>
      <h2 className="text-3xl sm:text-4xl font-semibold tracking-tight">{title}</h2>
      {subtitle && (
        <p className="text-sm sm:text-base text-muted-foreground leading-relaxed">{subtitle}</p>
      )}
    </div>
  );
}

function FeatureCell({
  icon: Icon,
  title,
  description,
}: {
  icon: React.ComponentType<{ className?: string }>;
  title: string;
  description: string;
}) {
  return (
    <div className="bg-card p-7 group transition-colors hover:bg-card/80">
      <div className="h-9 w-9 rounded-md bg-primary-soft text-primary flex items-center justify-center mb-4 transition-transform group-hover:scale-105">
        <Icon className="h-4 w-4" />
      </div>
      <h3 className="text-base font-semibold text-foreground mb-1">{title}</h3>
      <p className="text-sm text-muted-foreground leading-relaxed">{description}</p>
    </div>
  );
}

function FlowStep({
  step,
  icon: Icon,
  title,
  description,
}: {
  step: string;
  icon: React.ComponentType<{ className?: string }>;
  title: string;
  description: string;
}) {
  return (
    <div className="relative rounded-xl border border-border bg-card p-6 card-hover">
      <div className="flex items-center justify-between mb-5">
        <span className="text-[11px] font-medium tracking-wider text-muted-foreground">
          STEP {step}
        </span>
        <div className="h-8 w-8 rounded-md bg-gradient-to-br from-primary to-primary/70 text-primary-foreground flex items-center justify-center shadow-sm">
          <Icon className="h-3.5 w-3.5" />
        </div>
      </div>
      <h3 className="text-sm font-semibold text-foreground mb-1">{title}</h3>
      <p className="text-xs text-muted-foreground leading-relaxed">{description}</p>
    </div>
  );
}

function StackTile({
  label,
  sub,
  icon: Icon,
}: {
  label: string;
  sub: string;
  icon: React.ComponentType<{ className?: string }>;
}) {
  return (
    <div className="rounded-xl border border-border bg-card p-5 card-hover text-center">
      <div className="mx-auto h-10 w-10 rounded-md bg-primary-soft text-primary flex items-center justify-center mb-3">
        <Icon className="h-4.5 w-4.5" />
      </div>
      <p className="text-sm font-semibold text-foreground">{label}</p>
      <p className="text-xs text-muted-foreground mt-0.5">{sub}</p>
    </div>
  );
}

function SecurityChip({
  icon: Icon,
  title,
  description,
}: {
  icon: React.ComponentType<{ className?: string }>;
  title: string;
  description: string;
}) {
  return (
    <div className="flex items-start gap-3 rounded-xl border border-border bg-card p-5">
      <div className="h-8 w-8 rounded-md bg-primary-soft text-primary flex items-center justify-center shrink-0">
        <Icon className="h-3.5 w-3.5" />
      </div>
      <div className="space-y-0.5">
        <h4 className="text-sm font-semibold text-foreground">{title}</h4>
        <p className="text-xs text-muted-foreground leading-relaxed">{description}</p>
      </div>
    </div>
  );
}

/* ============================================================
   Hero preview tile — a polished mock of the admin dashboard.
   ============================================================ */
function HeroPreview() {
  return (
    <div className="relative rounded-2xl border border-border bg-card shadow-lg overflow-hidden">
      {/* Window chrome */}
      <div className="flex items-center gap-2 px-4 py-2.5 border-b border-border bg-muted/40">
        <span className="h-2.5 w-2.5 rounded-full bg-destructive/40" />
        <span className="h-2.5 w-2.5 rounded-full bg-warning/50" />
        <span className="h-2.5 w-2.5 rounded-full bg-success/50" />
        <span className="ml-3 text-[11px] font-mono text-muted-foreground">
          localhost:3000/admin
        </span>
      </div>

      <div className="grid grid-cols-12 min-h-[340px]">
        {/* Sidebar mock */}
        <div className="hidden md:flex md:col-span-3 border-r border-border bg-card flex-col">
          <div className="px-4 py-3 border-b border-border flex items-center gap-2">
            <div className="h-5 w-5 rounded bg-foreground" />
            <span className="h-2.5 w-20 rounded bg-muted" />
          </div>
          <div className="p-3 space-y-1">
            <div className="px-2 py-1 text-[9px] uppercase tracking-wider text-muted-foreground">
              Access Control
            </div>
            {[
              { active: true, label: 'Overview' },
              { active: false, label: 'Roles & Permissions' },
              { active: false, label: 'User Management' },
              { active: false, label: 'Audit Logs' },
            ].map((item, i) => (
              <div
                key={i}
                className={`flex items-center gap-2 px-2 py-1.5 rounded-md ${
                  item.active ? 'bg-primary-soft' : ''
                }`}
              >
                <span className={`h-3 w-3 rounded ${item.active ? 'bg-primary' : 'bg-muted'}`} />
                <span
                  className={`h-2 rounded ${item.active ? 'bg-primary/70 w-12' : 'bg-muted w-16'}`}
                />
              </div>
            ))}
          </div>
        </div>

        {/* Main mock */}
        <div className="col-span-12 md:col-span-9 p-6 space-y-6">
          <div className="space-y-1.5">
            <div className="h-2 w-20 rounded bg-muted" />
            <div className="h-5 w-48 rounded bg-foreground/80" />
            <div className="h-2.5 w-72 rounded bg-muted" />
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
            {[1, 2, 3, 4, 5].map((i) => (
              <div key={i} className="rounded-lg border border-border p-3 space-y-2">
                <div className="h-5 w-5 rounded bg-muted" />
                <div className="h-5 w-10 rounded bg-foreground/80" />
                <div className="h-2 w-12 rounded bg-muted" />
              </div>
            ))}
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            {[1, 2, 3].map((i) => (
              <div key={i} className="rounded-lg border border-border p-3 space-y-2">
                <div className="flex items-center justify-between">
                  <div className="h-6 w-6 rounded bg-primary-soft" />
                  <div className="h-3 w-3 rounded bg-muted" />
                </div>
                <div className="h-2.5 w-16 rounded bg-foreground/70" />
                <div className="h-2 w-full rounded bg-muted" />
                <div className="h-7 w-full rounded bg-muted/60 mt-2" />
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

/* ============================================================
   Architecture diagram — schematic, on-brand.
   ============================================================ */
function ArchitectureDiagram() {
  return (
    <div className="rounded-2xl border border-border bg-card p-8 sm:p-10">
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <ArchTile
          tag="Browser"
          title="Next.js"
          subtitle="port 3000"
          items={['Auth API routes (/api/auth/*)', 'User admin routes', 'UI rendering']}
        />
        <div className="hidden lg:flex items-center justify-center">
          <div className="text-center space-y-2">
            <div className="text-[11px] font-mono text-muted-foreground bg-muted px-2 py-1 rounded inline-block">
              /api/v1/* → rewrite
            </div>
            <ArrowRight className="h-5 w-5 text-muted-foreground/60 mx-auto" />
            <div className="text-[10px] uppercase tracking-wider text-muted-foreground">
              same-origin · no CORS
            </div>
          </div>
        </div>
        <ArchTile
          tag="API"
          title="FastAPI"
          subtitle="port 8000"
          items={[
            'All database operations',
            'Router → Service → Repository',
            'RBAC permission guards',
          ]}
        />
      </div>

      <div className="mt-6 pt-6 border-t border-border">
        <div className="flex flex-col sm:flex-row items-center sm:items-stretch gap-4">
          <div className="flex-1 rounded-xl border border-border bg-muted/30 p-5 flex items-start gap-4">
            <div className="h-9 w-9 rounded-md bg-foreground text-background flex items-center justify-center shrink-0">
              <Database className="h-4 w-4" />
            </div>
            <div>
              <p className="text-sm font-semibold text-foreground">Supabase</p>
              <p className="text-xs text-muted-foreground mt-0.5">
                PostgreSQL (RLS + UUID v7) · Auth (GoTrue + JWT claims hook)
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function ArchTile({
  tag,
  title,
  subtitle,
  items,
}: {
  tag: string;
  title: string;
  subtitle: string;
  items: string[];
}) {
  return (
    <div className="rounded-xl border border-border bg-background p-5 space-y-3">
      <div className="flex items-baseline justify-between">
        <p className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
          {tag}
        </p>
        <p className="text-[11px] font-mono text-muted-foreground">{subtitle}</p>
      </div>
      <p className="text-base font-semibold text-foreground">{title}</p>
      <ul className="space-y-1.5">
        {items.map((item) => (
          <li key={item} className="flex items-start gap-2 text-xs text-muted-foreground">
            <span className="mt-1 h-1 w-1 rounded-full bg-primary shrink-0" />
            <span>{item}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
