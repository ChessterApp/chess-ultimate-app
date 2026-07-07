import type { Metadata, Viewport } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import { ClerkProvider } from '@clerk/nextjs'
import { NextIntlClientProvider } from 'next-intl';
import { getLocale, getMessages } from 'next-intl/server';
import "./globals.css";
import "../styles/chess-animations.css";
import ClientShell from "@/components/ClientShell";
import ServiceWorkerRegistration from "@/components/ServiceWorkerRegistration";
import PrefetchManager from "@/components/PrefetchManager";
import LocalStorageMigration from "@/components/LocalStorageMigration";
import { PowerSyncProvider } from "@/lib/powersync/PowerSyncProvider";
import { OrganizationProvider } from "@/contexts/OrganizationContext";
import BrandingInjector from "@/components/BrandingInjector";
import ImpersonationBanner from "@/components/super-admin/ImpersonationBanner";
import { buildMetadata } from "@/lib/org-metadata";
import { loadOrgFromHeaders } from "@/lib/org-from-headers";
import { buildClerkLocalization } from "@/lib/clerk-localization";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const viewport: Viewport = {
  width: 'device-width',
  initialScale: 1,
  viewportFit: 'cover',
};

export async function generateMetadata(): Promise<Metadata> {
  const org = await loadOrgFromHeaders();
  return buildMetadata(org);
}

export default async function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode
}>) {
  const locale = await getLocale();
  const messages = await getMessages();

  const org = await loadOrgFromHeaders();
  const clerkLocalization = buildClerkLocalization(locale, org?.name || 'Chesster');

  return (
    <ClerkProvider localization={clerkLocalization}>
      <html lang={locale} suppressHydrationWarning>
        <head>
          <link rel="preconnect" href="https://clerk.chesster.io" />
          <link rel="preconnect" href="https://accounts.clerk.services" />
          <link rel="dns-prefetch" href="https://clerk.chesster.io" />
          <link rel="manifest" href="/manifest.webmanifest" />
          <meta name="theme-color" content={org?.primaryColor || '#9333ea'} />
          <meta name="mobile-web-app-capable" content="yes" />
          <meta name="apple-mobile-web-app-status-bar-style" content="default" />
          {org && org.customCss ? (
            <style dangerouslySetInnerHTML={{ __html: org.customCss }} />
          ) : null}
        </head>
        <body className={`${geistSans.variable} ${geistMono.variable} antialiased`} suppressHydrationWarning>
          <OrganizationProvider org={org}>
            <BrandingInjector />
            <ImpersonationBanner />
            <NextIntlClientProvider messages={messages}>
              <PowerSyncProvider>
                <LocalStorageMigration />
                <ServiceWorkerRegistration />
                <PrefetchManager />
                <ClientShell>
                  {children}
                </ClientShell>
              </PowerSyncProvider>
            </NextIntlClientProvider>
          </OrganizationProvider>
        </body>
      </html>
    </ClerkProvider>
  )
}
