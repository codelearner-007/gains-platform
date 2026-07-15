import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import { Analytics } from '@vercel/analytics/next';
import CookieConsent from "@/components/common/Cookies";
import { GoogleAnalytics } from '@next/third-parties/google';
import ToastMount from '@/components/common/ToastMount';
import { publicSettings } from "@/lib/core/public-settings";

const inter = Inter({
  subsets: ['latin'],
  display: 'swap',
  variable: '--font-sans',
});

const productName = publicSettings.NEXT_PUBLIC_PRODUCTNAME;

export const metadata: Metadata = {
  title: {
    default: `${productName} · Assessment analytics for schools`,
    template: `%s · ${productName}`,
  },
  description:
    "GAINS turns your school's assessments into clear reports on students, standards, and growth over time.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  const gaID = publicSettings.NEXT_PUBLIC_GA_MEASUREMENT_ID;
  return (
    <html lang="en" className={inter.variable}>
    <body className={inter.className}>
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:absolute focus:z-[100] focus:top-4 focus:left-4 focus:px-4 focus:py-2 focus:bg-background focus:text-foreground focus:rounded-md focus:ring-2 focus:ring-ring focus:outline-none"
      >
        Skip to main content
      </a>
      {children}
      <ToastMount />
      <Analytics />
      <CookieConsent />
      {gaID && <GoogleAnalytics gaId={gaID} />}
    </body>
    </html>
  );
}
