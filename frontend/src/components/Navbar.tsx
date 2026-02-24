"use client"

import { useState, useEffect } from "react"
import { useRouter } from "next/navigation"
import { useAuth, UserButton } from "@clerk/nextjs"
import { useLocale } from 'next-intl'
import Image from "next/image"
import LanguageSwitcher from "@/components/LanguageSwitcher"

export default function NavBar() {
  const { isSignedIn } = useAuth()
  const router = useRouter()
  const locale = useLocale()

  // Prevent hydration mismatch: useAuth returns different values on server vs client
  const [mounted, setMounted] = useState(false)
  useEffect(() => { setMounted(true) }, [])

  return (
    <nav className="bg-white border-b border-gray-100">
      <div className="container mx-auto px-4 py-3">
        <div className="flex items-center justify-between">
          {/* Logo - always clickable */}
          <button
            onClick={() => router.push(isSignedIn ? "/dashboard" : "/")}
            className="text-xl font-bold text-gray-900 hover:text-purple-600 transition-colors flex items-center gap-1"
          >
            <Image src="/static/images/chesster-logo-v3.png" alt="Chesster" width={24} height={24} className="w-6 h-6" /> Chesster
          </button>

          {/* Right side: Language Switcher + User Avatar (if signed in) */}
          <div className="flex items-center gap-3">
            <LanguageSwitcher currentLocale={locale} variant="minimal" />

            {mounted && isSignedIn && (
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
