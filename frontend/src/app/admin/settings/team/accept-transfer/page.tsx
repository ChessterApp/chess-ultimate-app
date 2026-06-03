'use client';

import { useEffect, useState } from 'react';
import { useSearchParams } from 'next/navigation';
import { displayLabel } from '@/lib/ownership-transfer';

/**
 * Accept page reached from the ownership-transfer invite email
 * (PRD §11.3 #3).
 *
 * Flow:
 *   1. GET /api/ownership-transfers/by-token/<token>  — show details
 *   2. If state is `invite_pending`, render "Accept" CTA
 *   3. POST .../accept → transitions to `accepted`, owner re-confirmation
 *      happens back in /admin/settings/team
 */
export default function AcceptTransferPage() {
  const search = useSearchParams();
  const token = search?.get('token') || '';
  const [state, setState] = useState<string | null>(null);
  const [email, setEmail] = useState<string | null>(null);
  const [expires, setExpires] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  useEffect(() => {
    if (!token) return;
    fetch(`/api/ownership-transfers/by-token/${token}`)
      .then(async (res) => {
        if (!res.ok) {
          setError(`Not found (${res.status})`);
          return;
        }
        const body = await res.json();
        setState(body.transfer.state);
        setEmail(body.transfer.invitee_email);
        setExpires(body.transfer.expires_at);
      })
      .catch((e) => setError(e?.message || 'load failed'));
  }, [token]);

  async function accept() {
    setBusy(true);
    setError(null);
    try {
      const res = await fetch(
        `/api/ownership-transfers/by-token/${token}/accept`,
        { method: 'POST' },
      );
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        setError(body.message || `Failed (${res.status})`);
        return;
      }
      setDone(true);
    } finally {
      setBusy(false);
    }
  }

  if (!token) {
    return <p className="p-8 text-center text-red-600">Missing token.</p>;
  }

  return (
    <div className="max-w-md mx-auto p-8 space-y-4">
      <h1 className="text-2xl font-bold">Accept ownership transfer</h1>

      {error && <p className="text-sm text-red-600">{error}</p>}

      {state && !done && (
        <div className="rounded-lg border border-gray-200 p-4 space-y-2">
          <p>
            <span className="text-gray-500">Invitee:</span>{' '}
            <span className="font-medium">{email}</span>
          </p>
          <p>
            <span className="text-gray-500">State:</span>{' '}
            <span className="font-medium">{displayLabel(state as never)}</span>
          </p>
          {expires && (
            <p>
              <span className="text-gray-500">Expires:</span>{' '}
              <span className="font-medium">
                {new Date(expires).toLocaleString()}
              </span>
            </p>
          )}
        </div>
      )}

      {state === 'invite_pending' && !done && (
        <button
          type="button"
          onClick={accept}
          disabled={busy}
          className="w-full rounded bg-blue-600 px-4 py-3 text-white font-semibold disabled:opacity-50"
        >
          Accept ownership
        </button>
      )}

      {done && (
        <p className="text-green-700 text-center">
          Accepted. The current owner will see your confirmation in their
          team settings and complete the transfer.
        </p>
      )}
    </div>
  );
}
