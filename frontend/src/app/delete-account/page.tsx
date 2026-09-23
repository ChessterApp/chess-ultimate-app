'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { useClerk } from '@clerk/nextjs'

const CONFIRM_WORD = 'DELETE'

const DELETION_ITEMS = [
  'Your account and sign-in credentials',
  'Your game history and saved games',
  'Course and lesson progress',
  'AI coach conversations',
  'Ratings, tournament entries and standings',
  'Subscription linkage',
]

export default function DeleteAccountPage() {
  const router = useRouter()
  const { signOut } = useClerk()

  const [confirmText, setConfirmText] = useState('')
  const [status, setStatus] = useState<'idle' | 'deleting'>('idle')
  const [error, setError] = useState<string | null>(null)

  const canDelete = confirmText.trim().toUpperCase() === CONFIRM_WORD && status === 'idle'

  const handleDelete = async () => {
    if (!canDelete) return
    setStatus('deleting')
    setError(null)

    try {
      const res = await fetch('/api/account/delete', { method: 'POST' })

      if (!res.ok) {
        // Surface a readable message; the API returns { error } (and a code for
        // the owns-organization case). Never leave the user in a half-deleted UI.
        let message = 'Something went wrong. Your account was not deleted. Please try again.'
        try {
          const body = await res.json()
          if (body?.error) message = body.error as string
        } catch {
          /* non-JSON error body — keep the generic message */
        }
        setError(message)
        setStatus('idle')
        return
      }

      // Deleted: end the Clerk session and land on the home page with a
      // confirmation banner.
      await signOut({ redirectUrl: '/?account_deleted=1' })
    } catch {
      setError('Network error. Your account was not deleted. Please try again.')
      setStatus('idle')
    }
  }

  return (
    <div className="min-h-screen bg-gray-50 pb-24">
      {/* Header */}
      <div className="bg-gradient-to-br from-red-600 to-red-800 text-white">
        <div className="container mx-auto px-4 py-6">
          <div className="flex items-center gap-3">
            <button
              onClick={() => router.back()}
              className="p-2 rounded-xl bg-white/10 hover:bg-white/20 transition-colors"
              aria-label="Go back"
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
              </svg>
            </button>
            <div>
              <h1 className="text-2xl font-bold">Delete Account</h1>
              <p className="text-red-200 text-sm">Permanently remove your account and data</p>
            </div>
          </div>
        </div>
      </div>

      <div className="container mx-auto px-4 py-6 space-y-6 animate-page-enter max-w-2xl">
        {/* What deletion does */}
        <div className="bg-white rounded-2xl shadow-md p-6">
          <h2 className="text-lg font-bold text-gray-900 mb-1">⚠️ This is permanent</h2>
          <p className="text-sm text-gray-500 mb-4">
            Deleting your account is <strong>irreversible</strong>. Once confirmed, we cannot
            recover it. The following will be permanently removed:
          </p>
          <ul className="space-y-2">
            {DELETION_ITEMS.map((item) => (
              <li key={item} className="flex items-start gap-2 text-sm text-gray-700">
                <svg className="w-5 h-5 text-red-500 flex-shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
                <span>{item}</span>
              </li>
            ))}
          </ul>
        </div>

        {/* Confirmation gate */}
        <div className="bg-white rounded-2xl shadow-md p-6">
          <h2 className="text-lg font-bold text-gray-900 mb-1">Confirm deletion</h2>
          <p className="text-sm text-gray-500 mb-4">
            Type <span className="font-mono font-bold text-gray-900">{CONFIRM_WORD}</span> below to
            enable the delete button.
          </p>

          <input
            type="text"
            value={confirmText}
            onChange={(e) => setConfirmText(e.target.value)}
            disabled={status === 'deleting'}
            placeholder={CONFIRM_WORD}
            autoComplete="off"
            aria-label={`Type ${CONFIRM_WORD} to confirm`}
            className="w-full rounded-xl border border-gray-300 px-4 py-3 text-gray-900 font-mono focus:outline-none focus:ring-2 focus:ring-red-500 focus:border-red-500 disabled:bg-gray-100 disabled:cursor-not-allowed"
          />

          {error && (
            <div
              role="alert"
              className="mt-4 rounded-xl bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-700"
            >
              {error}
            </div>
          )}

          <button
            onClick={handleDelete}
            disabled={!canDelete}
            className={`mt-5 w-full rounded-xl px-4 py-3 font-bold text-white transition-colors ${
              canDelete
                ? 'bg-red-600 hover:bg-red-700'
                : 'bg-gray-300 cursor-not-allowed'
            }`}
          >
            {status === 'deleting' ? 'Deleting…' : 'Delete my account'}
          </button>

          <button
            onClick={() => router.back()}
            disabled={status === 'deleting'}
            className="mt-3 w-full rounded-xl px-4 py-3 font-medium text-gray-600 hover:bg-gray-100 transition-colors disabled:cursor-not-allowed"
          >
            Cancel
          </button>
        </div>
      </div>
    </div>
  )
}
