import Link from 'next/link';
import Image from 'next/image';
import type { Metadata } from 'next';
import {
  Compass,
  Layers,
  LineChart,
  Users,
  Zap,
  ShieldCheck,
  TrendingUp,
} from 'lucide-react';
import { SiteNav } from '@/components/common/SiteNav';
import { SiteFooter } from '@/components/common/SiteFooter';
import { Button } from '@/components/ui/button';
import { getMe } from '@/lib/server/me';

export const metadata: Metadata = {
  description:
    'GAINS turns your school’s assessments into reports teachers trust. See how every student, class, and standard is doing, and know exactly where to focus next.',
};

const VALUE_CARDS = [
  {
    icon: Compass,
    title: 'Know where to look.',
    description:
      "A clear view of each learner's performance across subjects and assessments, ready to share with teachers and families.",
  },
  {
    icon: Layers,
    title: 'One shared picture.',
    description:
      'See exactly where each class stands on the standards that matter, so reteaching time goes where it counts.',
  },
  {
    icon: LineChart,
    title: 'See it change.',
    description:
      'Follow progress across the year, from the first assessment to the last, for one student or the whole school.',
  },
];

const STEPS = [
  {
    number: '01',
    title: 'Connect your assessment data',
    description:
      "We work with your existing systems to bring assessment results into GAINS automatically, so there's nothing new to maintain.",
  },
  {
    number: '02',
    title: 'Teachers see the reports',
    description:
      'Every student, class, and standard rolls up into reports teachers can read in minutes, not hours.',
  },
  {
    number: '03',
    title: 'Track growth over time',
    description: 'As new assessments come in, GAINS keeps the picture current, so progress is always visible.',
  },
];

const FEATURE_CARDS = [
  {
    icon: Users,
    title: 'Built for teachers',
    description: 'Reports are written in plain language teachers trust and can act on right away.',
  },
  {
    icon: Zap,
    title: 'Ready in days',
    description: 'Onboarding is fast — most schools are up and running in days, not months.',
  },
  {
    icon: ShieldCheck,
    title: 'Private by default',
    description: 'Student data stays scoped to your school, with access controlled down to the classroom.',
  },
  {
    icon: TrendingUp,
    title: 'Grows with you',
    description: 'Add more assessments, classes, or campuses without changing how reporting works.',
  },
];

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
          <Image
            src="/home/hero-bg.jpg"
            alt="Teacher and students reviewing assessment results together"
            fill
            priority
            sizes="100vw"
            className="object-cover"
          />
          <div className="absolute inset-0 bg-gradient-to-r from-background via-background/85 to-background/40" />

          <div className="relative max-w-7xl mx-auto px-6 pt-20 pb-20 lg:pt-28 lg:pb-28">
            <div className="max-w-2xl">
              <span className="inline-flex items-center rounded-full border border-border bg-muted px-3 py-1 text-xs font-medium text-muted-foreground">
                For schools, with schools
              </span>

              <h1 className="mt-6 text-4xl sm:text-5xl lg:text-6xl font-semibold tracking-tight leading-[1.08]">
                You already have <br /> the answers.
                <br />
                <span className="text-gradient-logo">GAINS makes <br /> them obvious.</span>
              </h1>

              <p className="mt-6 text-base sm:text-lg text-muted-foreground max-w-xl leading-relaxed">
                GAINS turns your school&apos;s assessments into reports teachers trust. See how
                every student, class, and standard is doing, and know exactly where to focus
                next.
              </p>

              <div className="mt-10 flex flex-col sm:flex-row gap-3">
                <Button asChild size="xl" variant="destructive">
                  <Link href={ctaHref}>{ctaLabel}</Link>
                </Button>
                <Button asChild size="xl" variant="outline">
                  <a href="https://edvancelearning.us/" rel="noopener noreferrer">
                    Talk to us
                  </a>
                </Button>
              </div>

              {!user && (
                <p className="mt-6 text-xs text-muted-foreground">
                  GAINS is available to partner schools by invitation.
                </p>
              )}
            </div>
          </div>
        </section>

        {/* ==================== WHY SCHOOLS CHOOSE US ==================== */}
        <section className="relative overflow-hidden border-t border-border/60 py-24 sm:py-32">
          <Image
            src="/home/exam.jpg"
            alt=""
            aria-hidden="true"
            width={200}
            height={200}
            className=" absolute left-4 top-1/2 -translate-x-[25%] -translate-y-1/2 opacity-[0.05]"
          />
          <div className="relative max-w-6xl mx-auto px-6">
            <div className="max-w-2xl mx-auto text-center">
              <p className="text-sm font-medium text-destructive">Why schools choose us</p>
              <h2 className="mt-3 text-3xl sm:text-4xl font-semibold tracking-tight">
                Clarity, not more dashboards.
              </h2>
              <p className="mt-4 text-base text-muted-foreground leading-relaxed">
                GAINS distills every assessment into a picture teachers and administrators can
                act on immediately — no spreadsheets, no guesswork.
              </p>
            </div>

            <div className="mt-14 grid grid-cols-1 md:grid-cols-3 gap-6">
              {VALUE_CARDS.map((card) => (
                <ValueCard key={card.title} {...card} />
              ))}
            </div>
          </div>
        </section>

        {/* ==================== HOW IT WORKS ==================== */}
        <section className="relative overflow-hidden border-t border-border/60 py-24 sm:py-32">
         <Image
            src="/home/online.jpg"
            alt=""
            aria-hidden="true"
            width={200}
            height={200}
            className=" absolute right-4 top-1/2 translate-x-[25%] -translate-y-1/2 opacity-[0.05]"
          />
          <div className="relative max-w-6xl mx-auto px-6">
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-12 lg:gap-16">
              {/* Steps */}
              <div>
                <p className="text-sm font-medium text-destructive">How it works</p>
                <h2 className="mt-3 text-3xl sm:text-4xl font-semibold tracking-tight">
                  It fits the way your school already works.
                </h2>
                <p className="mt-4 text-base text-muted-foreground leading-relaxed">
                  No new workflows to learn and no extra data entry for teachers. GAINS plugs
                  into the assessment data you already collect.
                </p>

                <ol className="mt-10 space-y-8">
                  {STEPS.map((step) => (
                    <Step key={step.number} {...step} />
                  ))}
                </ol>
              </div>

              {/* Feature grid */}
              <ul className="grid grid-cols-1 sm:grid-cols-2 gap-6 content-start">
                {FEATURE_CARDS.map((feature) => (
                  <FeatureCard key={feature.title} {...feature} />
                ))}
              </ul>
            </div>
          </div>
        </section>

        {/* ==================== CTA BAND ==================== */}
        <section className="relative overflow-hidden border-t border-border bg-foreground text-background py-24 sm:py-32">
          <Image
            src="/home/footer-bg.avif"
            alt=""
            aria-hidden="true"
            fill
            sizes="100vw"
            className="object-cover grayscale"
          />
          <div className="absolute inset-0 bg-foreground/80" />
          <div className="relative max-w-3xl mx-auto px-6 text-center space-y-6">
            <h2 className="text-3xl sm:text-4xl font-semibold tracking-tight">
              Bring <span className="text-gradient-logo">GAINS</span> to your school.
            </h2>
            <p className="text-sm sm:text-base text-background/70 leading-relaxed max-w-xl mx-auto">
              We work with schools directly to get their assessment data flowing and their
              teachers reporting in days, not months.
            </p>
            <div className="flex flex-col sm:flex-row items-center justify-center gap-3 pt-2">
              <Button asChild size="xl" variant="destructive">
                <a href="tel:+19543254346">
                  Contact Edvance Learning
                </a>
              </Button>
              <Button
                asChild
                size="xl"
                variant="outline"
                className="border-background/40 text-background hover:bg-background/10 hover:text-background"
              >
                <Link href={ctaHref}>{ctaLabel}</Link>
              </Button>
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
      <div className="h-11 w-11 rounded-xl bg-destructive/10 text-destructive flex items-center justify-center mb-5">
        <Icon className="h-5 w-5" />
      </div>
      <h3 className="text-lg font-semibold text-foreground mb-2">{title}</h3>
      <p className="text-sm text-muted-foreground leading-relaxed">{description}</p>
    </div>
  );
}

function FeatureCard({
  icon: Icon,
  title,
  description,
}: {
  icon: React.ComponentType<{ className?: string }>;
  title: string;
  description: string;
}) {
  return (
    <li className="rounded-2xl border border-border bg-card p-6 card-hover">
      <div className="h-9 w-9 rounded-lg bg-destructive/10 text-destructive flex items-center justify-center mb-4">
        <Icon className="h-4 w-4" />
      </div>
      <h3 className="text-sm font-semibold text-foreground mb-1.5">{title}</h3>
      <p className="text-xs text-muted-foreground leading-relaxed">{description}</p>
    </li>
  );
}

function Step({
  number,
  title,
  description,
}: {
  number: string;
  title: string;
  description: string;
}) {
  return (
    <li className="flex gap-4">
      <div className="h-9 w-9 shrink-0 rounded-full bg-destructive text-destructive-foreground flex items-center justify-center text-xs font-semibold">
        {number}
      </div>
      <div>
        <h3 className="text-base font-semibold text-foreground mb-1">{title}</h3>
        <p className="text-sm text-muted-foreground leading-relaxed">{description}</p>
      </div>
    </li>
  );
}
