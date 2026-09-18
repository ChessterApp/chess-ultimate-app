'use client'

/**
 * Family card on the profile page.
 *
 * Lists every verified Chess Empire member linked to this account (name,
 * relationship tag, link status), lets the parent remove a child/other link
 * (with an explicit confirm that spells out that school-side registrations are
 * NOT cancelled), and hosts the "add family member" panel. Fetches from
 * `GET /api/chess-empire/link/members`; renders nothing until the account has
 * at least one verified link, so a fully-unlinked user sees no empty card.
 *
 * The `self` link cannot be removed here (out of scope — it's effectively
 * "delete my Chess Empire identity"); only child/other rows get a remove
 * control. Single-member accounts still see the card so a solo user can
 * discover the family feature and add a child.
 */
import { useEffect, useState } from 'react'
import { useTranslations } from 'next-intl'
import AddFamilyMember from '@/components/empire/AddFamilyMember'

type Relationship = 'self' | 'child' | 'other'

interface FamilyMember {
  studentId: string
  name: string | null
  relationship: Relationship
  status: string
}

export default function FamilySection() {
  const t = useTranslations('family')
  const tct = useTranslations('ceTournaments')

  const [members, setMembers] = useState<FamilyMember[] | null>(null)
  const [loaded, setLoaded] = useState(false)
  const [confirmingId, setConfirmingId] = useState<string | null>(null)
  const [removingId, setRemovingId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    fetch('/api/chess-empire/link/members')
      .then((r) => (r.ok ? r.json() : null))
      .then((data: { members?: FamilyMember[] } | null) => {
        if (cancelled) return
        setMembers(data?.members ?? [])
      })
      .catch(() => {
        if (!cancelled) setMembers([])
      })
      .finally(() => {
        if (!cancelled) setLoaded(true)
      })
    return () => {
      cancelled = true
    }
  }, [])

  const remove = async (studentId: string) => {
    setRemovingId(studentId)
    setError(null)
    try {
      const res = await fetch(
        `/api/chess-empire/link/members/${encodeURIComponent(studentId)}`,
        { method: 'DELETE' },
      )
      if (!res.ok) {
        setError(t('removeError'))
        return
      }
      setMembers((prev) => (prev ?? []).filter((m) => m.studentId !== studentId))
      setConfirmingId(null)
    } catch {
      setError(t('removeError'))
    } finally {
      setRemovingId(null)
    }
  }

  // Hide entirely until we know there's at least one verified link.
  if (!loaded || !members || members.length === 0) return null

  const relationshipLabel = (rel: Relationship) => tct(`relationship.${rel}`)

  return (
    <div className="bg-white rounded-2xl shadow-md p-6">
      <h2 className="text-lg font-bold text-gray-900 mb-1">👨‍👩‍👧 {t('title')}</h2>
      <p className="text-xs text-gray-400 mb-4">{t('subtitle')}</p>

      <ul className="space-y-3">
        {members.map((m) => {
          const removable = m.relationship === 'child' || m.relationship === 'other'
          const name = m.name || t('unknownMember')
          const isConfirming = confirmingId === m.studentId
          return (
            <li
              key={m.studentId}
              className="rounded-xl border border-gray-100 bg-gray-50 p-3"
            >
              <div className="flex items-center justify-between gap-3">
                <div className="min-w-0">
                  <div className="font-semibold text-gray-900 truncate">{name}</div>
                  <div className="mt-0.5 flex items-center gap-2 text-xs">
                    <span className="rounded-full bg-purple-100 px-2 py-0.5 font-medium text-purple-700">
                      {relationshipLabel(m.relationship)}
                    </span>
                    <span className="text-green-600">{t('statusVerified')}</span>
                  </div>
                </div>
                {removable && !isConfirming && (
                  <button
                    type="button"
                    onClick={() => {
                      setError(null)
                      setConfirmingId(m.studentId)
                    }}
                    aria-label={t('removeMemberAria', { name })}
                    className="shrink-0 rounded-lg border border-red-200 px-3 py-1.5 text-sm font-medium text-red-600 hover:bg-red-50 transition-colors"
                  >
                    {t('removeMember')}
                  </button>
                )}
              </div>

              {isConfirming && (
                <div className="mt-3 rounded-lg border border-red-200 bg-red-50 p-3">
                  <p className="text-sm font-semibold text-gray-900">
                    {t('removeConfirmTitle', { name })}
                  </p>
                  <p className="mt-1 text-xs text-gray-600">{t('removeConfirmBody')}</p>
                  {error && <p className="mt-2 text-xs text-red-600">{error}</p>}
                  <div className="mt-3 flex gap-2">
                    <button
                      type="button"
                      onClick={() => remove(m.studentId)}
                      disabled={removingId === m.studentId}
                      className="rounded-lg bg-red-600 px-3 py-1.5 text-sm font-semibold text-white hover:bg-red-700 disabled:opacity-50 transition-colors"
                    >
                      {removingId === m.studentId ? t('removing') : t('removeConfirmButton')}
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        setConfirmingId(null)
                        setError(null)
                      }}
                      disabled={removingId === m.studentId}
                      className="rounded-lg border border-gray-300 bg-white px-3 py-1.5 text-sm font-medium text-gray-600 hover:bg-gray-50 disabled:opacity-50 transition-colors"
                    >
                      {t('removeCancelButton')}
                    </button>
                  </div>
                </div>
              )}
            </li>
          )
        })}
      </ul>

      <div className="mt-4">
        <AddFamilyMember />
      </div>
    </div>
  )
}
