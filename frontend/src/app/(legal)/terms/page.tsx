import type { Metadata } from 'next';
import { publicSettings } from '@/lib/core/public-settings';

export const metadata: Metadata = {
  title: 'Terms of Service',
  description: 'The terms governing your use of the service.',
};

export default function TermsPage() {
  const productName = publicSettings.NEXT_PUBLIC_PRODUCTNAME;
  const updated = 'May 5, 2026';

  return (
    <article className="max-w-3xl mx-auto px-6 py-16 sm:py-24">
      <header className="space-y-3 pb-8 mb-10 border-b border-border">
        <p className="text-xs font-medium uppercase tracking-wider text-primary">Legal</p>
        <h1 className="text-3xl sm:text-4xl font-semibold tracking-tight">Terms of Service</h1>
        <p className="text-sm text-muted-foreground">Last updated {updated}</p>
      </header>

      <div className="space-y-8 text-sm text-foreground/90 leading-relaxed">
        <Section title="Agreement">
          By creating an account or using {productName}, you agree to these terms. This is a
          starter-template placeholder — replace it with terms that fit your jurisdiction and
          product before going to production.
        </Section>

        <Section title="Your account">
          <ul className="list-disc pl-5 space-y-1.5 text-muted-foreground">
            <li>You are responsible for keeping your credentials secure.</li>
            <li>You must provide accurate information during registration.</li>
            <li>You agree not to share your account or attempt to access other users&apos; data.</li>
          </ul>
        </Section>

        <Section title="Acceptable use">
          You agree not to use the service to: violate applicable law, infringe intellectual
          property, transmit malware, attempt to bypass security or rate-limiting controls, or
          impersonate another person or organization.
        </Section>

        <Section title="Service availability">
          We provide the service on an &ldquo;as is&rdquo; basis. We will make a reasonable effort to keep
          the service available, but we don&apos;t guarantee uninterrupted operation. Replace this
          section with the SLA you intend to offer.
        </Section>

        <Section title="Termination">
          You may delete your account at any time from{' '}
          <Link href="/app/user-settings">Account Settings</Link>. We may suspend or terminate
          accounts that violate these terms. Audit log records may be retained as required by law.
        </Section>

        <Section title="Changes">
          We may update these terms from time to time. Material changes will be communicated via
          email or in-app notification when applicable.
        </Section>

        <Section title="Contact">
          Replace this paragraph with your legal/support contact before going live.
        </Section>
      </div>
    </article>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="space-y-3">
      <h2 className="text-base font-semibold text-foreground">{title}</h2>
      <div className="text-muted-foreground leading-relaxed">{children}</div>
    </section>
  );
}

function Link({ href, children }: { href: string; children: React.ReactNode }) {
  return (
    <a href={href} className="text-primary hover:underline underline-offset-4">
      {children}
    </a>
  );
}
