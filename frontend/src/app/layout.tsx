import type { Metadata } from "next";
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

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

// Clerk localization strings per locale
const clerkLocalizations: Record<string, Record<string, unknown>> = {
  en: {
    signIn: {
      start: {
        title: 'Sign in to Chesster',
        subtitle: 'Welcome back! Please sign in to continue',
      },
    },
    signUp: {
      start: {
        title: 'Create your Chesster account',
        subtitle: 'Start your chess journey today',
      },
    },
    formFieldInputPlaceholder__firstName: 'Name (optional)',
    formFieldInputPlaceholder__emailAddress: 'Email',
    formFieldInputPlaceholder__password: 'Password',
    formFieldLabel__firstName: 'Name',
    formFieldLabel__emailAddress: 'Email',
    formFieldLabel__password: 'Password',
  },
  ru: {
    signIn: {
      start: {
        title: 'Войти в Chesster',
        subtitle: 'С возвращением! Войдите, чтобы продолжить',
      },
    },
    signUp: {
      start: {
        title: 'Создайте аккаунт Chesster',
        subtitle: 'Начните своё шахматное путешествие сегодня',
      },
    },
    formFieldInputPlaceholder__firstName: 'Имя (необязательно)',
    formFieldInputPlaceholder__emailAddress: 'Электронная почта',
    formFieldInputPlaceholder__password: 'Пароль',
    formFieldLabel__firstName: 'Имя',
    formFieldLabel__emailAddress: 'Электронная почта',
    formFieldLabel__password: 'Пароль',
  },
  kz: {
    signIn: {
      start: {
        title: 'Chesster-ге кіру',
        subtitle: 'Қайта қош келдіңіз! Жалғастыру үшін кіріңіз',
      },
    },
    signUp: {
      start: {
        title: 'Chesster аккаунтын жасау',
        subtitle: 'Шахмат саяхатыңызды бүгін бастаңыз',
      },
    },
    formFieldInputPlaceholder__firstName: 'Аты (міндетті емес)',
    formFieldInputPlaceholder__emailAddress: 'Электрондық пошта',
    formFieldInputPlaceholder__password: 'Құпия сөз',
    formFieldLabel__firstName: 'Аты',
    formFieldLabel__emailAddress: 'Электрондық пошта',
    formFieldLabel__password: 'Құпия сөз',
  },
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
  const clerkLocalization = clerkLocalizations[locale] || clerkLocalizations.en;

  const org = await loadOrgFromHeaders();

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
          <link rel="icon" href={org?.faviconUrl || '/static/images/default-favicon.ico'} />
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
