import Link from 'next/link';
import type { Metadata } from 'next';
import { GraduationCap, Target, TrendingUp } from 'lucide-react';
import { SiteNav } from '@/components/common/SiteNav';
import { SiteFooter } from '@/components/common/SiteFooter';
import { BrandWordmark } from '@/components/common/BrandWordmark';
import { Button } from '@/components/ui/button';
import { getMe } from '@/lib/server/me';

export const metadata: Metadata = {
  // No page-level title: the root layout's `default` ("GAINS · Assessment
  // analytics for schools") is the right, descriptive landing-tab title.
  description:
    'GAINS turns your school’s assessments into reports teachers trust. See how every student, class, and standard is doing, and know exactly where to focus next.',
};

export default async function Home() {
  // Adapt the CTAs to auth state: a signed-in visitor should never see "Sign in".
  const user = await getMe();
  const ctaHref = user ? '/app' : '/auth/login';
  const ctaLabel = user ? 'Go to dashboard' : 'Sign in';

  return (
    <div className="min-h-screen flex flex-col bg-background text-foreground selection:bg-primary/30">
      <SiteNav />
      <main id="main-content" className="flex-1 pt-14">
        {/* ==================== HERO ==================== */}
        <section className="relative overflow-hidden">
          <div className="absolute inset-0 bg-dotgrid opacity-50 pointer-events-none" />
          <div className="absolute inset-x-0 top-0 h-[700px] bg-brand-glow pointer-events-none" />

          <div className="relative max-w-4xl mx-auto px-6 pt-24 pb-24 lg:pt-32 lg:pb-32 text-center">
            <BrandWordmark height={64} priority className="mx-auto mb-10" />

            <h1 className="text-4xl sm:text-5xl lg:text-6xl font-semibold tracking-tight leading-[1.08]">
              Every assessment has a story.
              <br />
              <span className="text-gradient-brand">GAINS tells it clearly.</span>
            </h1>

            <p className="mt-6 text-base sm:text-lg text-muted-foreground max-w-2xl mx-auto leading-relaxed">
              GAINS turns your school&apos;s assessments into reports teachers trust. See how every
              student, class, and standard is doing, and know exactly where to focus next.
            </p>

            <div className="mt-10 flex justify-center">
              <Button asChild size="xl" className="btn-glow">
                <Link href={ctaHref}>{ctaLabel}</Link>
              </Button>
            </div>

            {!user && (
              <p className="mt-6 text-xs text-muted-foreground">
                GAINS is available to partner schools by invitation.
              </p>
            )}
          </div>
        </section>

        {/* ==================== VALUE ==================== */}
        <section className="border-t border-border/60 py-24 sm:py-32">
          <div className="max-w-6xl mx-auto px-6">
            <h2 className="text-3xl sm:text-4xl font-semibold tracking-tight text-center max-w-2xl mx-auto">
              One platform, the whole picture.
            </h2>

            <div className="mt-14 grid grid-cols-1 md:grid-cols-3 gap-6">
              <ValueCard
                icon={GraduationCap}
                title="Know every student."
                description="A clear view of each learner's performance across subjects and assessments, ready to share with teachers and families."
              />
              <ValueCard
                icon={Target}
                title="Master every standard."
                description="See exactly where each class stands on the standards that matter, so reteaching time goes where it counts."
              />
              <ValueCard
                icon={TrendingUp}
                title="Watch growth happen."
                description="Follow progress across the year, from the first assessment to the last, for one student or the whole school."
              />
            </div>
          </div>
        </section>

        {/* ==================== CTA BAND ==================== */}
        <section className="relative overflow-hidden border-t border-border py-24 sm:py-32">
          <div className="absolute inset-0 bg-brand-glow pointer-events-none" />
          <div className="relative max-w-3xl mx-auto px-6">
            <div className="rounded-3xl border border-border bg-card p-10 sm:p-14 text-center space-y-6 card-hover">
              <h2 className="text-3xl sm:text-4xl font-semibold tracking-tight">
                Bring GAINS to your school.
              </h2>
              <p className="text-sm sm:text-base text-muted-foreground leading-relaxed max-w-xl mx-auto">
                We work with schools directly to get their assessment data flowing and their
                teachers reporting in days, not months.
              </p>
              <div className="flex flex-col sm:flex-row items-center justify-center gap-3 pt-2">
                <Button asChild size="xl" className="btn-glow">
                  <a href="https://edvancelearning.us/" rel="noopener noreferrer">Contact Edvance Learning</a>
                </Button>
                <Button asChild size="xl" variant="outline">
                  <Link href={ctaHref}>{ctaLabel}</Link>
                </Button>
              </div>
            </div>
          </div>
        </section>
      </main>
      <SiteFooter />
    </div>
  );
}

function ValueCard({
  icon: Icon,
  title,
  description,
}: {
  icon: React.ComponentType<{ className?: string }>;
  title: string;
  description: string;
}) {
  return (
    <div className="rounded-2xl border border-border bg-card p-7 card-hover">
      <div className="h-11 w-11 rounded-xl bg-primary-soft text-primary flex items-center justify-center mb-5">
        <Icon className="h-5 w-5" />
      </div>
      <h3 className="text-lg font-semibold text-foreground mb-2">{title}</h3>
      <p className="text-sm text-muted-foreground leading-relaxed">{description}</p>
    </div>
  );
}
