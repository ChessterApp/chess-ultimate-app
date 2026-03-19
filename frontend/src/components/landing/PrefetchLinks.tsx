'use client'

import Link from 'next/link'

/**
 * Invisible prefetch links for main navigation routes.
 * These links are hidden but allow Next.js to prefetch the routes in the background.
 */
export function PrefetchLinks() {
  return (
    <div style={{ display: 'none' }}>
      <Link href="/dashboard" prefetch={true}>Dashboard</Link>
      <Link href="/debut" prefetch={true}>Debut</Link>
      <Link href="/learn" prefetch={true}>Learn</Link>
      <Link href="/puzzle" prefetch={true}>Puzzle</Link>
    </div>
  )
}
