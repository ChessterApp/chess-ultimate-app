import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import { ClerkProvider } from '@clerk/nextjs'
import { NextIntlClientProvider } from 'next-intl';
import { getLocale, getMessages } from 'next-intl/server';
import "./globals.css";
import "../styles/chess-animations.css";
import NavBar from "@/components/Navbar";
import { BottomNavigation, BottomNavSpacer } from "@/components/ui/BottomNavigation";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Chess Empire - AI-Powered Chess Training",
  description: "Plug-and-play chess training with your choice of AI provider. Convert OpenAI, Claude, or Gemini model into chess-aware Chessbuddy and get personalized live chat training. Chess Empire integrates with Stockfish 17.1 engine, chess databases and to better align with position context, making LLMs chess aware.",
  
  // Open Graph metadata (for Facebook, LinkedIn, Discord, etc.)
  openGraph: {
    title: "Chess Empire - AI-Powered Chess Training",
    description: "Transform any AI model into your personal chessbuddy. Get live training with OpenAI, Claude, or Gemini integrated with Stockfish 17.1 engine.",
    url: "https://www.chessempire.com/", // Replace with your actual domain
    siteName: "Chess Empire",
    images: [
      {
        url: "static/images/agineowl-og.png", // Optional square version (1200x1200px)
        width: 1200,
        height: 1200,
        alt: "Chess Empire Logo",
      },
    ],
    locale: "en_US",
    type: "website",
  },
  
  // Twitter Card metadata
  twitter: {
    card: "summary_large_image",
    title: "Chess Empire - AI-Powered Chess Training",
    description: "Transform any AI model into your personal chess coach. Get live training with OpenAI, Claude, or Gemini integrated with Stockfish 17.1.",
    images: ["static/images/agineowl-og.png"], // Same image as Open Graph
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

// Custom localization for Clerk components
const clerkLocalization = {
  formFieldInputPlaceholder__firstName: 'Name (optional)',
  formFieldInputPlaceholder__emailAddress: 'Email',
  formFieldInputPlaceholder__password: 'Password',
  formFieldLabel__firstName: 'Name',
  formFieldLabel__emailAddress: 'Email',
  formFieldLabel__password: 'Password',
};

export default async function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode
}>) {
  const locale = await getLocale();
  const messages = await getMessages();

  return (
    <ClerkProvider localization={clerkLocalization}>
      <html lang={locale}>
        <body className={`${geistSans.variable} ${geistMono.variable} antialiased`}>
          <NextIntlClientProvider messages={messages}>
            <NavBar/>
            <main className="pb-16 md:pb-0">
              {children}
            </main>
            <BottomNavigation />
            <BottomNavSpacer />
          </NextIntlClientProvider>
        </body>
      </html>
    </ClerkProvider>
  )
}