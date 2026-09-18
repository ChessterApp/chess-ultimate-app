'use client';

/**
 * "Join family" consent landing page — the target of the invite email.
 *
 * The link only forms when the signed-in target explicitly accepts here, so
 * this page NEVER auto-accepts on load: it presents Join / Decline. An
 * email-targeted invite may only be accepted by the matching account (enforced
 * server-side), and an unlinked visitor is sent to sign in first.
 */
import { use, useState } from 'react';
import Link from 'next/link';
import { useAuth } from '@clerk/nextjs';

type Phase = 'idle' | 'working' | 'accepted' | 'declined' | 'error';

const ERROR_COPY: Record<string, string> = {
  not_found: "This invitation link is invalid or has already been used.",
  not_pending: 'This invitation is no longer active.',
  email_mismatch:
    'This invitation was sent to a different email address. Sign in with that account to accept.',
  accepter_not_linked:
    'Link your own Chess Empire account first, then open this invitation again.',
};

export default function FamilyJoinPage({
  params,
}: {
  params: Promise<{ token: string }>;
}) {
  const { token } = use(params);
  const { isLoaded, isSignedIn } = useAuth();
  const [phase, setPhase] = useState<Phase>('idle');
  const [error, setError] = useState<string | null>(null);

  const act = async (action: 'accept' | 'reject') => {
    setPhase('working');
    setError(null);
    try {
      const res = await fetch('/api/chess-empire/link/invite/accept', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ token, action }),
      });
      const body = (await res.json().catch(() => ({}))) as { error?: string };
      if (!res.ok) {
        setError(ERROR_COPY[body.error ?? ''] ?? 'Something went wrong. Please try again.');
        setPhase('error');
        return;
      }
      setPhase(action === 'accept' ? 'accepted' : 'declined');
    } catch {
      setError('Network error. Please try again.');
      setPhase('error');
    }
  };

  const shell = (children: React.ReactNode) => (
    <main className="mx-auto flex min-h-[70vh] max-w-md flex-col justify-center px-6 py-12">
      <div className="rounded-2xl border border-gray-100 bg-white p-6 shadow-md">
        <h1 className="mb-2 text-xl font-bold text-gray-900">👨‍👩‍👧 Join a Chess Empire family</h1>
        {children}
      </div>
    </main>
  );

  if (!isLoaded) {
    return shell(<p className="text-sm text-gray-500">Loading…</p>);
  }

  if (!isSignedIn) {
    const redirect = `/family/join/${encodeURIComponent(token)}`;
    return shell(
      <>
        <p className="mb-4 text-sm text-gray-600">
          Sign in to accept this family invitation.
        </p>
        <Link
          href={`/sign-in?redirect_url=${encodeURIComponent(redirect)}`}
          className="inline-block rounded-lg bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700"
        >
          Sign in
        </Link>
      </>,
    );
  }

  if (phase === 'accepted') {
    return shell(
      <p className="text-sm text-green-700">
        You&apos;re now family. You can register each other for tournaments.
      </p>,
    );
  }
  if (phase === 'declined') {
    return shell(<p className="text-sm text-gray-600">Invitation declined.</p>);
  }

  return shell(
    <>
      <p className="mb-4 text-sm text-gray-600">
        Accepting links your accounts so you can register each other for
        tournaments. Nothing happens until you choose.
      </p>
      {error && <p className="mb-3 text-sm text-red-600">{error}</p>}
      <div className="flex gap-2">
        <button
          type="button"
          onClick={() => act('accept')}
          disabled={phase === 'working'}
          className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700 disabled:opacity-50"
        >
          {phase === 'working' ? 'Working…' : 'Join family'}
        </button>
        <button
          type="button"
          onClick={() => act('reject')}
          disabled={phase === 'working'}
          className="rounded-lg border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-600 hover:bg-gray-50 disabled:opacity-50"
        >
          Decline
        </button>
      </div>
    </>,
  );
}
