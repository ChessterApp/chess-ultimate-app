'use client';

import { useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import { useOrganization } from '@/contexts/OrganizationContext';
import {
  canConfirm,
  canRevoke,
  type Transfer,
  type TransferState,
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
  const t = useTranslations('schoolOnboarding.admin.team');

  const [transfers, setTransfers] = useState<Transfer[]>([]);
  const [inviteEmail, setInviteEmail] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function stateLabel(state: TransferState): string {
    return t(`states.${state}`);
  }

  async function refresh() {
    if (!orgId) return;
    try {
      const res = await fetch(
        `/api/admin/organizations/${orgId}/ownership-transfers`,
      );
      if (!res.ok) {
        setError(t('loadFailed', { status: res.status }));
        return;
      }
      const body = await res.json();
      setTransfers(body.transfers || []);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : t('loadException'));
    }
  }

  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
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
        setError(body.message || t('failureFallback', { status: res.status }));
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
        setError(body.message || t('failureFallback', { status: res.status }));
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
        <h1 className="text-2xl font-bold">{t('heading')}</h1>
        <p className="text-sm text-gray-500">{t('description')}</p>
      </header>

      <section className="rounded-lg border border-gray-200 p-4 space-y-3">
        <h2 className="font-semibold">{t('inviteHeading')}</h2>
        <div className="flex gap-2">
          <input
            type="email"
            placeholder={t('emailPlaceholder')}
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
            {t('sendInvite')}
          </button>
        </div>
        {error && <p className="text-sm text-red-600">{error}</p>}
      </section>

      <section>
        <h2 className="font-semibold mb-2">{t('historyHeading')}</h2>
        {transfers.length === 0 ? (
          <p className="text-sm text-gray-500">{t('empty')}</p>
        ) : (
          <ul className="divide-y divide-gray-100 border border-gray-200 rounded">
            {transfers.map((tr) => (
              <li key={tr.id} className="flex items-center justify-between p-3">
                <div>
                  <div className="font-medium">{tr.invitee_email}</div>
                  <div className="text-xs text-gray-500">
                    {stateLabel(tr.state)} ·{' '}
                    {t('expires', {
                      date: new Date(tr.expires_at).toLocaleDateString(),
                    })}
                  </div>
                </div>
                <div className="flex gap-2">
                  {canRevoke(tr.state) && (
                    <button
                      type="button"
                      onClick={() => actOn(tr.id, 'revoke')}
                      disabled={busy}
                      className="text-sm rounded border border-gray-300 px-2 py-1 hover:bg-gray-50"
                    >
                      {t('revoke')}
                    </button>
                  )}
                  {canConfirm(tr.state) && (
                    <button
                      type="button"
                      onClick={() => actOn(tr.id, 'confirm')}
                      disabled={busy}
                      className="text-sm rounded bg-green-600 text-white px-2 py-1 hover:bg-green-700"
                    >
                      {t('confirmTransfer')}
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
