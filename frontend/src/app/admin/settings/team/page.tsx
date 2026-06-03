'use client';

import { useEffect, useState } from 'react';
import { useOrganization } from '@/contexts/OrganizationContext';
import {
  canConfirm,
  canRevoke,
  displayLabel,
  type Transfer,
} from '@/lib/ownership-transfer';

/**
 * Owner-facing ownership-transfer admin page (PRD §11.3 #3).
 *
 * Lets the current owner:
 *   - invite a new owner by email (creates an `invite_pending` row)
 *   - revoke an in-flight transfer
 *   - confirm an accepted transfer (swaps roles atomically)
 */
export default function TeamSettingsPage() {
  const { org } = useOrganization();
  const orgId = org?.id || '';

  const [transfers, setTransfers] = useState<Transfer[]>([]);
  const [inviteEmail, setInviteEmail] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function refresh() {
    if (!orgId) return;
    try {
      const res = await fetch(
        `/api/admin/organizations/${orgId}/ownership-transfers`,
      );
      if (!res.ok) {
        setError(`Failed to load (${res.status})`);
        return;
      }
      const body = await res.json();
      setTransfers(body.transfers || []);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'load failed');
    }
  }

  useEffect(() => {
    refresh();
  }, [orgId]);

  async function createInvite() {
    if (!orgId || !inviteEmail) return;
    setBusy(true);
    setError(null);
    try {
      const res = await fetch(
        `/api/admin/organizations/${orgId}/ownership-transfers`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ invitee_email: inviteEmail }),
        },
      );
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        setError(body.message || `Failed (${res.status})`);
        return;
      }
      setInviteEmail('');
      refresh();
    } finally {
      setBusy(false);
    }
  }

  async function actOn(id: string, kind: 'revoke' | 'confirm') {
    setBusy(true);
    setError(null);
    try {
      const res = await fetch(
        `/api/admin/organizations/${orgId}/ownership-transfers/${id}/${kind}`,
        { method: 'POST' },
      );
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        setError(body.message || `Failed (${res.status})`);
        return;
      }
      refresh();
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="max-w-3xl mx-auto p-6 space-y-6">
      <header>
        <h1 className="text-2xl font-bold">Team & ownership</h1>
        <p className="text-sm text-gray-500">
          Transfer ownership of your school to another admin (PRD §11.3 #3).
        </p>
      </header>

      <section className="rounded-lg border border-gray-200 p-4 space-y-3">
        <h2 className="font-semibold">Invite a new owner</h2>
        <div className="flex gap-2">
          <input
            type="email"
            placeholder="assistant@school.com"
            value={inviteEmail}
            onChange={(e) => setInviteEmail(e.target.value)}
            className="flex-1 rounded border border-gray-300 px-3 py-2"
          />
          <button
            type="button"
            onClick={createInvite}
            disabled={busy || !inviteEmail}
            className="rounded bg-blue-600 px-4 py-2 text-white font-semibold disabled:opacity-50"
          >
            Send invite
          </button>
        </div>
        {error && <p className="text-sm text-red-600">{error}</p>}
      </section>

      <section>
        <h2 className="font-semibold mb-2">Transfer history</h2>
        {transfers.length === 0 ? (
          <p className="text-sm text-gray-500">No transfers yet.</p>
        ) : (
          <ul className="divide-y divide-gray-100 border border-gray-200 rounded">
            {transfers.map((t) => (
              <li key={t.id} className="flex items-center justify-between p-3">
                <div>
                  <div className="font-medium">{t.invitee_email}</div>
                  <div className="text-xs text-gray-500">
                    {displayLabel(t.state)} ·{' '}
                    expires {new Date(t.expires_at).toLocaleDateString()}
                  </div>
                </div>
                <div className="flex gap-2">
                  {canRevoke(t.state) && (
                    <button
                      type="button"
                      onClick={() => actOn(t.id, 'revoke')}
                      disabled={busy}
                      className="text-sm rounded border border-gray-300 px-2 py-1 hover:bg-gray-50"
                    >
                      Revoke
                    </button>
                  )}
                  {canConfirm(t.state) && (
                    <button
                      type="button"
                      onClick={() => actOn(t.id, 'confirm')}
                      disabled={busy}
                      className="text-sm rounded bg-green-600 text-white px-2 py-1 hover:bg-green-700"
                    >
                      Confirm transfer
                    </button>
                  )}
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
