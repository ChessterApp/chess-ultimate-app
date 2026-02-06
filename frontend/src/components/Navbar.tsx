"use client"

import { useRouter } from "next/navigation"
import { useAuth, UserButton } from "@clerk/nextjs"
import { useLocale } from 'next-intl'
import LanguageSwitcher from "@/components/LanguageSwitcher"

export default function NavBar() {
  const { isSignedIn } = useAuth()
  const router = useRouter()
  const locale = useLocale()

  return (
    <nav className="bg-white border-b border-gray-100">
      <div className="container mx-auto px-4 py-3">
        <div className="flex items-center justify-between">
          {/* Logo - always clickable */}
          <button
            onClick={() => router.push(isSignedIn ? "/dashboard" : "/")}
            className="text-xl font-bold text-gray-900 hover:text-purple-600 transition-colors flex items-center gap-1"
          >
            ♟️ Chesster
          </button>

          {/* Right side: Language Switcher + User Avatar (if signed in) */}
          <div className="flex items-center gap-3">
            <LanguageSwitcher currentLocale={locale} variant="minimal" />

            {isSignedIn && (
              <UserButton
                appearance={{
                  elements: {
                    avatarBox: "w-9 h-9"
                  }
                }}
              />
            )}
          </div>
        </div>
      </div>
    </nav>
  )
}
