'use client'

import { useAuth } from '@clerk/nextjs'
import { useRouter } from 'next/navigation'
import { useEffect } from 'react'
import LoadingScreen from '@/components/LoadingScreen'

export function LandingPageClientWrapper({ children }: { children: React.ReactNode }) {
  const { isSignedIn, isLoaded } = useAuth()
  const router = useRouter()

  // Redirect to dashboard if already signed in
  useEffect(() => {
    if (isLoaded && isSignedIn) {
      router.push('/dashboard')
    }
  }, [isLoaded, isSignedIn, router])

  // Show loading animation if not loaded
  if (!isLoaded) {
    return <LoadingScreen isVisible={true} />
  }

  // Show loading animation while redirecting
  if (isSignedIn) {
    return <LoadingScreen isVisible={true} />
  }

  return <>{children}</>
}
