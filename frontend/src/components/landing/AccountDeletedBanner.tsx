'use client'

import { useState } from 'react'
import { useSearchParams } from 'next/navigation'

/**
 * Shows a one-time confirmation after a successful account deletion. The delete
 * flow signs the user out and lands them on `/?account_deleted=1`; this reads
 * that param client-side (in a Suspense boundary) so the landing page stays
 * statically rendered / ISR for normal visits.
 */
export function AccountDeletedBanner() {
  const params = useSearchParams()
  const [dismissed, setDismissed] = useState(false)

  if (dismissed || params?.get('account_deleted') !== '1') return null

  return (
    <div className="fixed top-0 left-0 right-0 z-[60] flex justify-center px-4 pt-4">
      <div
        role="status"
        className="flex items-center gap-3 rounded-xl bg-green-600 px-4 py-3 text-white shadow-lg max-w-md w-full"
      >
        <svg className="w-5 h-5 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
        </svg>
        <span className="text-sm font-medium flex-1">Your account has been deleted.</span>
        <button
          onClick={() => setDismissed(true)}
          aria-label="Dismiss"
          className="p-1 rounded-lg hover:bg-white/20 transition-colors"
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>
    </div>
  )
}
