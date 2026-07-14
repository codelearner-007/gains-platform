import Link from 'next/link';
import { ArrowLeft, GraduationCap, Target, TrendingUp, FileText } from 'lucide-react';
import { Providers } from '@/components/common/Providers';
import { BrandWordmark } from '@/components/common/BrandWordmark';

export default function AuthLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const highlights = [
    {
      icon: GraduationCap,
      title: 'Student reports',
      description: 'A complete picture of every learner, ready to share.',
    },
    {
      icon: Target,
      title: 'Standards mastery',
      description: 'Know where each class stands on every standard.',
    },
    {
      icon: TrendingUp,
      title: 'Growth over time',
      description: 'Progress across the year, not just one test.',
    },
    {
      icon: FileText,
      title: 'Question insight',
      description: 'See how every question landed, at a glance.',
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
            <BrandWordmark height={26} priority />
          </Link>
        </div>

        <div className="mt-6 sm:mx-auto sm:w-full sm:max-w-md">
          <Providers>{children}</Providers>
        </div>
      </div>

      {/* Right: brand panel */}
      <div className="hidden lg:flex lg:w-1/2 relative overflow-hidden border-l border-border">
        <div className="absolute inset-0 bg-auth-panel" />
        <div className="absolute inset-0 bg-dotgrid opacity-60" />

        <div className="relative z-10 w-full flex items-center justify-center p-12">
          <div className="max-w-md space-y-10">
            <div className="space-y-3">
              <span className="inline-flex items-center gap-2 rounded-full border border-border/60 bg-card/40 px-3 py-1 text-xs font-medium text-foreground backdrop-blur">
                <GraduationCap className="h-3 w-3" />
                By invitation
              </span>
              <h2 className="text-3xl font-semibold tracking-tight text-foreground leading-tight">
                Assessment clarity{' '}
                <span className="text-gradient-brand">for every classroom.</span>
              </h2>
              <p className="text-sm text-muted-foreground leading-relaxed">
                GAINS turns your school&apos;s assessments into clear, trusted
                reports on students, standards, and growth.
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

            <p className="text-xs text-muted-foreground pt-4 border-t border-border/40">
              GAINS. A product of{' '}
              <a
                href="https://edvancelearning.us/"
                rel="noopener noreferrer"
                className="font-medium text-foreground hover:text-primary transition-colors"
              >
                Edvance Learning
              </a>
              .
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
