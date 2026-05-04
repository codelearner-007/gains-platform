import Link from 'next/link';
import { ArrowLeft, Shield, Key, LayoutDashboard, ScrollText, Sparkles } from 'lucide-react';
import { Providers } from '@/components/common/Providers';
import { publicSettings } from '@/lib/core/public-settings';

export default function AuthLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const productName = publicSettings.NEXT_PUBLIC_PRODUCTNAME;

  const highlights = [
    {
      icon: Shield,
      title: 'Authentication & MFA',
      description: 'Email/password, SSO, and TOTP multi-factor — wired and ready.',
    },
    {
      icon: Key,
      title: 'Role-Based Access Control',
      description: 'Granular permissions, hierarchical roles, JWT-claim guards.',
    },
    {
      icon: LayoutDashboard,
      title: 'Admin Dashboard',
      description: 'User management, RBAC, and audit logs from day one.',
    },
    {
      icon: ScrollText,
      title: 'Audit Trail',
      description: 'Tamper-resistant log of every privileged action.',
    },
  ];

  return (
    <div className="flex min-h-screen bg-background">
      {/* Left: form */}
      <div className="w-full lg:w-1/2 flex flex-col justify-center py-12 px-4 sm:px-6 lg:px-8 relative">
        <Link
          href="/"
          className="absolute left-6 top-6 sm:left-8 sm:top-8 inline-flex items-center text-sm text-muted-foreground hover:text-foreground transition-colors"
        >
          <ArrowLeft className="w-4 h-4 mr-2" />
          Back to home
        </Link>

        <div className="sm:mx-auto sm:w-full sm:max-w-md">
          <Link href="/" className="flex items-center justify-center gap-2 mb-2">
            <div className="h-9 w-9 rounded-lg bg-foreground text-background flex items-center justify-center">
              <Sparkles className="h-4.5 w-4.5" />
            </div>
            <span className="text-lg font-semibold tracking-tight text-foreground">
              {productName}
            </span>
          </Link>
        </div>

        <div className="mt-6 sm:mx-auto sm:w-full sm:max-w-md">
          <Providers>{children}</Providers>
        </div>
      </div>

      {/* Right: brand panel */}
      <div className="hidden lg:flex lg:w-1/2 relative overflow-hidden border-l border-border">
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_top_right,oklch(0.62_0.22_273_/_0.30),transparent_55%),radial-gradient(ellipse_at_bottom_left,oklch(0.65_0.22_305_/_0.25),transparent_55%)]" />
        <div className="absolute inset-0 bg-dotgrid opacity-60" />

        <div className="relative z-10 w-full flex items-center justify-center p-12">
          <div className="max-w-md space-y-10">
            <div className="space-y-3">
              <span className="inline-flex items-center gap-2 rounded-full border border-border/60 bg-card/40 px-3 py-1 text-xs font-medium text-foreground backdrop-blur">
                <Sparkles className="h-3 w-3" />
                Production-grade starter
              </span>
              <h2 className="text-3xl font-semibold tracking-tight text-foreground leading-tight">
                Ship your SaaS{' '}
                <span className="text-gradient-brand">on solid foundations</span>
              </h2>
              <p className="text-sm text-muted-foreground leading-relaxed">
                Auth, RBAC, an admin panel, and an audit trail — implemented,
                hardened, and ready to extend.
              </p>
            </div>

            <ul className="space-y-3">
              {highlights.map((item) => (
                <li
                  key={item.title}
                  className="flex items-start gap-3 rounded-lg border border-border/60 bg-card/40 backdrop-blur p-4 transition-colors hover:border-primary/30"
                >
                  <div className="p-2 rounded-md bg-primary-soft text-primary shrink-0">
                    <item.icon className="h-4 w-4" />
                  </div>
                  <div className="space-y-0.5">
                    <h4 className="text-sm font-medium text-foreground leading-none">
                      {item.title}
                    </h4>
                    <p className="text-xs text-muted-foreground leading-relaxed">
                      {item.description}
                    </p>
                  </div>
                </li>
              ))}
            </ul>

            <p className="text-xs text-muted-foreground/80 pt-4 border-t border-border/40">
              {productName} — Next.js + FastAPI + Supabase
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
