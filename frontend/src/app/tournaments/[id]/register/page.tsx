'use client';

import { useEffect, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { useAuth } from '@clerk/nextjs';
import Link from 'next/link';

// Fallback banner text when the server does not supply a message (server stays
// the source of truth for the League C level gate).
const LEVEL_TOO_LOW_FALLBACK =
  "League C tournaments require Level 2+. You're on Level 1 — complete your Level 1 lessons to unlock registration.";

export default function TournamentRegisterPage() {
  const params = useParams();
  const router = useRouter();
  const { getToken } = useAuth();
  const tournamentId = params?.id as string;

  const [playerName, setPlayerName] = useState('');
  const [rating, setRating] = useState('');
  const [ageCategory, setAgeCategory] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');
  // When set, the student is blocked from registering (League C level gate).
  const [levelBlock, setLevelBlock] = useState('');

  // Pre-check eligibility on load: a Level 1 student on a League C tournament
  // is warned and the submit button is disabled before they even try.
  useEffect(() => {
    if (!tournamentId) return;
    let cancelled = false;

    (async () => {
      try {
        const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL || '';
        const token = await getToken();
        const res = await fetch(`${backendUrl}/api/tournaments/${tournamentId}/eligibility`, {
          headers: token ? { Authorization: `Bearer ${token}` } : {},
        });
        if (!res.ok) return;
        const data = await res.json();
        if (!cancelled && data.eligible === false && data.code === 'level_too_low') {
          setLevelBlock(data.message || LEVEL_TOO_LOW_FALLBACK);
        }
      } catch {
        // Non-blocking: server remains the source of truth on submit.
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [tournamentId, getToken]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!playerName.trim() || levelBlock) return;
    setSubmitting(true);
    setError('');

    try {
      const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL || '';
      const token = await getToken();
      const body: Record<string, unknown> = {
        player_name: playerName.trim(),
      };
      if (rating) body.rating = parseInt(rating);
      if (ageCategory) body.age_category = ageCategory;

      const res = await fetch(`${backendUrl}/api/tournaments/${tournamentId}/register`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify(body),
      });

      if (res.ok) {
        router.push(`/tournaments/${tournamentId}`);
      } else {
        const data = await res.json();
        if (data.code === 'level_too_low') {
          // Fallback: render the server rejection in the same friendly banner.
          setLevelBlock(data.message || LEVEL_TOO_LOW_FALLBACK);
        } else {
          setError(data.error || 'Registration failed');
        }
      }
    } catch {
      setError('Network error. Please try again.');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="max-w-lg mx-auto px-4 py-8">
      <Link href={`/tournaments/${tournamentId}`} className="text-sm text-blue-600 dark:text-blue-400 hover:underline mb-4 inline-block">
        &larr; Back to Tournament
      </Link>

      <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100 mb-6">
        Tournament Registration
      </h1>

      <form onSubmit={handleSubmit} className="space-y-6">
        {levelBlock && (
          <div
            role="alert"
            className="rounded-lg border border-amber-300 bg-amber-50 dark:bg-amber-900/20 dark:border-amber-700 p-3 text-sm text-amber-800 dark:text-amber-200"
          >
            {levelBlock}
          </div>
        )}
        {error && (
          <div className="rounded-lg border border-red-200 bg-red-50 dark:bg-red-900/20 dark:border-red-800 p-3 text-sm text-red-700 dark:text-red-300">
            {error}
          </div>
        )}

        <section className="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 p-6">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-4">Player Information</h2>
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                Full Name *
              </label>
              <input
                type="text"
                value={playerName}
                onChange={e => setPlayerName(e.target.value)}
                required
                placeholder="Your full name"
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-sm"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                Current Rating
              </label>
              <input
                type="number"
                value={rating}
                onChange={e => setRating(e.target.value)}
                placeholder="e.g. 1500"
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-sm"
              />
              <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                Internal or FIDE rating (optional)
              </p>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                Age Category
              </label>
              <select
                value={ageCategory}
                onChange={e => setAgeCategory(e.target.value)}
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-sm"
              >
                <option value="">None</option>
                <option value="U8">U8</option>
                <option value="U10">U10</option>
                <option value="U12">U12</option>
                <option value="U14">U14</option>
                <option value="U16">U16</option>
                <option value="U18">U18</option>
                <option value="open">Open</option>
                <option value="senior">Senior (60+)</option>
              </select>
            </div>
          </div>
        </section>

        <button
          type="submit"
          disabled={submitting || !playerName.trim() || !!levelBlock}
          className="w-full px-6 py-3 text-sm font-medium text-white rounded-lg disabled:opacity-50 transition-colors"
          style={{ backgroundColor: 'var(--brand-primary)' }}
        >
          {submitting ? 'Registering...' : 'Register'}
        </button>
      </form>
    </div>
  );
}
