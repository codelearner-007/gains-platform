import type { Metadata } from 'next';
import Image from 'next/image';
import { SiteNav } from '@/components/common/SiteNav';
import { PageTocNav } from '@/components/common/PageTocNav';
import { publicSettings } from '@/lib/core/public-settings';
import { CONTACT_PHONE, CONTACT_PHONE_HREF } from '@/lib/core/contact';

export const metadata: Metadata = {
  title: 'Privacy Policy',
  description: 'How we collect, use, and protect your information.',
};

const SECTIONS = [
  {
    title: 'What we collect',
    slug: 'what-we-collect',
    items: [
      'Account information (email, name, hashed password)',
      'Profile preferences (avatar, timezone, display settings)',
      'Authentication metadata (active sessions, MFA factors)',
      'Audit log entries for privileged actions you perform',
      'Standard request metadata (IP address, user agent)',
    ],
  },
  {
    title: 'How we use it',
    slug: 'how-we-use-it',
    text: 'We use this data to operate and secure the service: authenticating you, enforcing access control, displaying your content, and producing tamper-resistant audit records of privileged actions for security and compliance purposes.',
  },
  {
    title: "What we don't do",
    slug: 'what-we-dont-do',
    items: [
      'We do not sell your personal information.',
      'We do not run third-party advertising trackers on this template by default.',
      'Any analytics integration you add (e.g. Google Analytics, Vercel Analytics) is yours to configure and disclose.',
    ],
  },
  {
    title: 'Your rights',
    slug: 'your-rights',
    text: (
      <>
        You can access, update, or delete your account at any time from{' '}
        <a href="/app/user-settings" className="text-primary hover:underline underline-offset-4">
          Account Settings
        </a>
        . Deleting your account permanently removes your auth record and profile; audit log
        entries that reference your past actions are retained for security purposes per
        applicable law.
      </>
    ),
  },
  {
    title: 'Contact',
    slug: 'contact',
    text: (
      <>
        Questions about this policy? Call us at{' '}
        <a href={CONTACT_PHONE_HREF} className="text-primary hover:underline underline-offset-4">
          {CONTACT_PHONE}
        </a>
        .
      </>
    ),
  },
];

export default function PrivacyPage() {
  const productName = publicSettings.NEXT_PUBLIC_PRODUCTNAME;
  const updated = 'May 5, 2026';

  return (
    <div className="min-h-screen flex flex-col bg-background text-foreground selection:bg-primary/30">
      <SiteNav />
      <main id="main-content" className="flex-1">
        {/* ==================== HEADER ==================== */}
        <section className="relative overflow-hidden">
          <Image
            src="/privacy/privacyBg.jpg"
            alt=""
            aria-hidden="true"
            fill
            priority
            sizes="100vw"
            className="object-cover"
          />
          <div className="absolute inset-0 bg-gradient-to-b from-background/50 via-background/60 to-background" />

          <div className="relative max-w-4xl mx-auto px-6 pt-24 pb-20 sm:pt-32 sm:pb-28 text-center">
            <h1 className="mt-6 text-4xl sm:text-5xl font-semibold tracking-tight drop-shadow-sm">
              <span className="text-gradient-logo">GAINS</span> POLICY
            </h1>
            <p className="mt-4 text-sm text-foreground/80">Last updated {updated}</p>
            <p className="mt-6 text-base text-foreground/90 leading-relaxed max-w-2xl mx-auto">
              This Privacy Policy describes how {productName} (&ldquo;we&rdquo;, &ldquo;us&rdquo;) collects, uses,
              and protects information when you use the application. This is a starter-template
              placeholder — replace it with the policy that matches your jurisdiction and product
              before going to production.
            </p>
          </div>
        </section>
        <div className='relative '>
          <Image
                src="/legal/privacy/privacyIcon1.png"
                alt=""
                aria-hidden="true"
                width={280}
                height={280}
                loading="lazy"
                className="hidden xl:block absolute -translate-x-[50%]  top-1/4 opacity-10 "
              />
              <Image
                src="/legal/privacy/privacyIcon2.png"
                alt=""
                aria-hidden="true"
                width={280}
                height={280}
                loading="lazy"
                className="hidden xl:block absolute right-0 bottom-1/4 translate-x-[55%] opacity-10 "
              />
              <div className="max-w-6xl mx-auto px-6 py-16 sm:py-20">
          

          <div className="lg:grid lg:grid-cols-[220px_1fr] lg:gap-16">
            {/* ==================== SIDEBAR TOC ==================== */}
            <PageTocNav sections={SECTIONS} />

            {/* ==================== CONTENT ==================== */}
            <div className="max-w-2xl space-y-14">
              
              {SECTIONS.map((section, index) => (
                <section key={section.slug} id={section.slug} className="space-y-3 scroll-mt-24">
                  <h2 className="flex items-center gap-3 font-serif text-2xl font-semibold text-foreground">
                    <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-destructive/10 text-sm font-semibold text-destructive">
                      {index + 1}
                    </span>
                    {section.title}
                  </h2>
                  <div className="text-base text-muted-foreground leading-relaxed">
                    {section.items ? (
                      <ul className="list-disc pl-5 space-y-1.5">
                        {section.items.map((item) => (
                          <li key={item}>{item}</li>
                        ))}
                      </ul>
                    ) : (
                      section.text
                    )}
                  </div>
                </section>
              ))}
            </div>
          </div>
        </div>
        </div>
        
      </main>
    </div>
  );
}
