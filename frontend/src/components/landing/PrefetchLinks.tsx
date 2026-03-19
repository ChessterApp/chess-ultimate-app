'use client'

import { useEffect } from 'react'
import { useRouter } from 'next/navigation'

/**
 * Programmatically prefetch top 3 navigation routes after initial page load.
 * Uses router.prefetch() for better control over prefetch timing.
 */
export function PrefetchLinks() {
  const router = useRouter()

  useEffect(() => {
    // Prefetch top 3 routes after initial page load
    const routes = ['/dashboard', '/debut', '/learn']

    routes.forEach(route => {
      router.prefetch(route)
    })
  }, [router])

  return null
}
