import type { Metadata } from 'next';
import Image from 'next/image';
import { PageTocNav } from '@/components/common/PageTocNav';
import { publicSettings } from '@/lib/core/public-settings';

export const metadata: Metadata = {
  title: 'Terms of Service',
  description: 'The terms governing your use of the service.',
};

const SECTIONS = [
  {
    title: 'Agreement',
    slug: 'agreement',
    text: (productName: string) => (
      <>
        By creating an account or using {productName}, you agree to these terms. This is a
        starter-template placeholder — replace it with terms that fit your jurisdiction and
        product before going to production.
      </>
    ),
  },
  {
    title: 'Your account',
    slug: 'your-account',
    items: [
      'You are responsible for keeping your credentials secure.',
      'You must provide accurate information during registration.',
      "You agree not to share your account or attempt to access other users' data.",
    ],
  },
  {
    title: 'Acceptable use',
    slug: 'acceptable-use',
    text: () => (
      <>
        You agree not to use the service to: violate applicable law, infringe intellectual
        property, transmit malware, attempt to bypass security or rate-limiting controls, or
        impersonate another person or organization.
      </>
    ),
  },
  {
    title: 'Service availability',
    slug: 'service-availability',
    text: () => (
      <>
        We provide the service on an &ldquo;as is&rdquo; basis. We will make a reasonable effort
        to keep the service available, but we don&apos;t guarantee uninterrupted operation.
        Replace this section with the SLA you intend to offer.
      </>
    ),
  },
  {
    title: 'Termination',
    slug: 'termination',
    text: () => (
      <>
        You may delete your account at any time from{' '}
        <a href="/app/user-settings" className="text-primary hover:underline underline-offset-4">
          Account Settings
        </a>
        . We may suspend or terminate accounts that violate these terms. Audit log records may be
        retained as required by law.
      </>
    ),
  },
  {
    title: 'Changes',
    slug: 'changes',
    text: () => (
      <>
        We may update these terms from time to time. Material changes will be communicated via
        email or in-app notification when applicable.
      </>
    ),
  },
  {
    title: 'Contact',
    slug: 'contact',
    text: () => <>Replace this paragraph with your legal/support contact before going live.</>,
  },
];

export default function TermsPage() {
  const productName = publicSettings.NEXT_PUBLIC_PRODUCTNAME;
  const updated = 'May 5, 2026';

  return (
    <div className="text-foreground selection:bg-primary/30">
      {/* ==================== HEADER ==================== */}
      <section className="relative overflow-hidden min-h-[320px] sm:min-h-[380px]">
        <Image
          src="/legal/terms/t&c.png"
          alt=""
          aria-hidden="true"
          fill
          priority
          sizes="100vw"
          className="object-cover"
        />
        {/* <div className="absolute inset-0 bg-gradient-to-b from-background/50 via-background/60 to-background" /> */}

        {/* <div className="relative max-w-4xl mx-auto px-6 pt-24 pb-20 sm:pt-32 sm:pb-28 text-center">
          <h1 className="mt-6 text-4xl sm:text-5xl font-semibold tracking-tight drop-shadow-sm">
            <span className="text-gradient-logo">GAINS</span> TERMS
          </h1>
          <p className="mt-4 text-sm text-foreground/80">Last updated {updated}</p>
          <p className="mt-6 text-base text-foreground/90 leading-relaxed max-w-2xl mx-auto">
            These Terms of Service govern your use of {productName}. This is a starter-template
            placeholder — replace it with terms that fit your jurisdiction and product before
            going to production.
          </p>
        </div> */}
      </section>

      <div className="relative">
        <Image
          src="/legal/terms/termsIcon1.jpg"
          alt=""
          aria-hidden="true"
          width={280}
          height={280}
          loading="lazy"
          className="hidden xl:block absolute -translate-x-[50%] top-1/4 opacity-10"
        />
        <Image
          src="/legal/terms/termsIcon2.jpg"
          alt=""
          aria-hidden="true"
          width={280}
          height={280}
          loading="lazy"
          className="hidden xl:block absolute right-0 bottom-1/4 translate-x-[55%] opacity-10"
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
                      section.text(productName)
                    )}
                  </div>
                </section>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
