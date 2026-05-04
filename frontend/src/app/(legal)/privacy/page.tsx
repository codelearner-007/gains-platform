import type { Metadata } from 'next';
import { publicSettings } from '@/lib/core/public-settings';

export const metadata: Metadata = {
  title: 'Privacy Policy',
  description: 'How we collect, use, and protect your information.',
};

export default function PrivacyPage() {
  const productName = publicSettings.NEXT_PUBLIC_PRODUCTNAME;
  const updated = 'May 5, 2026';

  return (
    <article className="max-w-3xl mx-auto px-6 py-16 sm:py-24">
      <header className="space-y-3 pb-8 mb-10 border-b border-border">
        <p className="text-xs font-medium uppercase tracking-wider text-primary">Legal</p>
        <h1 className="text-3xl sm:text-4xl font-semibold tracking-tight">Privacy Policy</h1>
        <p className="text-sm text-muted-foreground">Last updated {updated}</p>
      </header>

      <div className="prose prose-sm max-w-none space-y-8 text-sm text-foreground/90 leading-relaxed">
        <Section title="Overview">
          This Privacy Policy describes how {productName} (&ldquo;we&rdquo;, &ldquo;us&rdquo;) collects, uses, and protects
          information when you use the application. This is a starter-template placeholder — replace
          it with the policy that matches your jurisdiction and product before going to production.
        </Section>

        <Section title="What we collect">
          <ul className="list-disc pl-5 space-y-1.5 text-muted-foreground">
            <li>Account information (email, name, hashed password)</li>
            <li>Profile preferences (avatar, timezone, display settings)</li>
            <li>Authentication metadata (active sessions, MFA factors)</li>
            <li>Audit log entries for privileged actions you perform</li>
            <li>Standard request metadata (IP address, user agent)</li>
          </ul>
        </Section>

        <Section title="How we use it">
          We use this data to operate and secure the service: authenticating you, enforcing access
          control, displaying your content, and producing tamper-resistant audit records of
          privileged actions for security and compliance purposes.
        </Section>

        <Section title="What we don&apos;t do">
          We do not sell your personal information. We do not run third-party advertising trackers
          on this template by default. Any analytics integration you add (e.g. Google Analytics,
          Vercel Analytics) is yours to configure and disclose.
        </Section>

        <Section title="Your rights">
          You can access, update, or delete your account at any time from{' '}
          <Link href="/app/user-settings">Account Settings</Link>. Deleting your account
          permanently removes your auth record and profile; audit log entries that reference your
          past actions are retained for security purposes per applicable law.
        </Section>

        <Section title="Contact">
          Questions about this policy? Replace this paragraph with your contact email or support
          link before going live.
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
