'use client'

import { useAuth } from '@clerk/nextjs'
import { useRouter } from 'next/navigation'
import { useEffect } from 'react'
import LoadingScreen from '@/components/LoadingScreen'

/**
 * Small client island that handles redirect logic without blocking server-side HTML rendering.
 * Renders nothing on server, handles redirect on client after hydration.
 */
export function LandingPageRedirect() {
  const { isSignedIn, isLoaded } = useAuth()
  const router = useRouter()

  // Redirect to dashboard if already signed in
  useEffect(() => {
    if (isLoaded && isSignedIn) {
      router.push('/dashboard')
    }
  }, [isLoaded, isSignedIn, router])

  // Show loading overlay only when redirecting (after auth is loaded and user is signed in)
  if (isLoaded && isSignedIn) {
    return <LoadingScreen isVisible={true} />
  }

  // Otherwise render nothing (server component handles the UI)
  return null
}

// Legacy wrapper - deprecated, use LandingPageRedirect instead
export function LandingPageClientWrapper({ children }: { children: React.ReactNode }) {
  const { isSignedIn, isLoaded } = useAuth()
  const router = useRouter()

  useEffect(() => {
    if (isLoaded && isSignedIn) {
      router.push('/dashboard')
    }
  }, [isLoaded, isSignedIn, router])

  if (!isLoaded) {
    return <LoadingScreen isVisible={true} />
  }

  if (isSignedIn) {
    return <LoadingScreen isVisible={true} />
  }

  return <>{children}</>
}
