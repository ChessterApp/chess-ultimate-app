import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import { ClerkProvider } from '@clerk/nextjs'
import { NextIntlClientProvider } from 'next-intl';
import { getLocale, getMessages } from 'next-intl/server';
import { headers } from 'next/headers';
import "./globals.css";
import "../styles/chess-animations.css";
import ClientShell from "@/components/ClientShell";
import ServiceWorkerRegistration from "@/components/ServiceWorkerRegistration";
import PrefetchManager from "@/components/PrefetchManager";
import LocalStorageMigration from "@/components/LocalStorageMigration";
import { PowerSyncProvider } from "@/lib/powersync/PowerSyncProvider";
import { OrganizationProvider, Organization, parseOrgFromHeaders } from "@/contexts/OrganizationContext";
import BrandingInjector from "@/components/BrandingInjector";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  metadataBase: new URL("https://chesster.io"),
  title: "Chesster - AI-Powered Chess Training",
  description: "Plug-and-play chess training with your choice of AI provider. Convert OpenAI, Claude, or Gemini model into chess-aware Chessbuddy and get personalized live chat training. Chesster integrates with Stockfish 17.1 engine, chess databases and to better align with position context, making LLMs chess aware.",

  // Open Graph metadata (for Facebook, LinkedIn, Discord, etc.)
  openGraph: {
    title: "Chesster - AI-Powered Chess Training",
    description: "Transform any AI model into your personal chessbuddy. Get live training with OpenAI, Claude, or Gemini integrated with Stockfish 17.1 engine.",
    url: "https://chesster.io",
    siteName: "Chesster",
    images: [
      {
        url: "/static/images/chesster-logo-og.png", // Chess knight mascot logo (1024x1024px)
        width: 1200,
        height: 1200,
        alt: "Chesster Logo",
      },
    ],
    locale: "en_US",
    type: "website",
  },
  
  // Twitter Card metadata
  twitter: {
    card: "summary_large_image",
    title: "Chesster - AI-Powered Chess Training",
    description: "Transform any AI model into your personal chess coach. Get live training with OpenAI, Claude, or Gemini integrated with Stockfish 17.1.",
    images: ["/static/images/chesster-logo-og.png"], // Chess knight mascot logo
  },
  
  // Additional metadata
  keywords: [
    "chess training",
    "AI chess coach",
    "OpenAI chess",
    "Claude chess",
    "Gemini chess",
    "Stockfish",
    "chess engine",
    "chess AI",
    "chess tutor",
    "chess learning",
    "chessempire"
  ],
  

 
  // Robots
  // robots: {
  //   index: true,
  //   follow: true,
  //   googleBot: {
  //     index: true,
  //     follow: true,
  //     'max-video-preview': -1,
  //     'max-image-preview': 'large',
  //     'max-snippet': -1,
  //   },
  // },
  
  // Additional Open Graph properties
  other: {
    // For better Discord embeds
    'theme-color': '#8209a3ff', // Replace with your brand color
  },
};

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

async function fetchOrgData(orgId: string, orgSlug: string): Promise<Organization | null> {
  try {
    const backendUrl = process.env.BACKEND_URL || 'http://localhost:5001';
    const res = await fetch(`${backendUrl}/api/admin/organizations/by-slug/${orgSlug}`, {
      next: { revalidate: 300 }, // Cache for 5 minutes
      signal: AbortSignal.timeout(3000),
    });
    if (!res.ok) return null;
    const data = await res.json();
    return {
      id: data.id || orgId,
      slug: data.slug || orgSlug,
      name: data.name || 'Chesster',
      logoUrl: data.logo_url || null,
      faviconUrl: data.favicon_url || null,
      primaryColor: data.primary_color || '#1a73e8',
      secondaryColor: data.secondary_color || '#ffffff',
      accentColor: data.accent_color || '#ffd700',
      landingPageConfig: data.landing_page_config || {},
      contactEmail: data.contact_email || null,
      status: data.status || 'active',
    };
  } catch {
    return null;
  }
}

export default async function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode
}>) {
  const locale = await getLocale();
  const messages = await getMessages();
  const clerkLocalization = clerkLocalizations[locale] || clerkLocalizations.en;

  // Read org headers injected by middleware
  const headersList = await headers();
  const orgInfo = parseOrgFromHeaders(headersList);
  let org: Organization | null = null;
  if (orgInfo) {
    org = await fetchOrgData(orgInfo.orgId, orgInfo.orgSlug);
  }

  return (
    <ClerkProvider localization={clerkLocalization}>
      <html lang={locale} suppressHydrationWarning>
        <head>
          <link rel="preconnect" href="https://clerk.chesster.io" />
          <link rel="preconnect" href="https://accounts.clerk.services" />
          <link rel="dns-prefetch" href="https://clerk.chesster.io" />
          <link rel="manifest" href="/manifest.json" />
          <meta name="theme-color" content={org?.primaryColor || '#9333ea'} />
          <meta name="mobile-web-app-capable" content="yes" />
          <meta name="apple-mobile-web-app-status-bar-style" content="default" />
          {org?.faviconUrl && (
            <link rel="icon" href={org.faviconUrl} />
          )}
        </head>
        <body className={`${geistSans.variable} ${geistMono.variable} antialiased`} suppressHydrationWarning>
          <OrganizationProvider org={org}>
            <BrandingInjector />
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