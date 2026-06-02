'use client';

import { useCallback, useEffect, useState } from 'react';
import { useOrganization } from '@/contexts/OrganizationContext';

// PRD §11.2 #4 — branded sender domain (Pro+).
//
// State machine mirrors /admin/settings/domain: pending → verifying → active
// / failed. Polls every 30s while pending/verifying so users see verification
// land without a reload.

type SenderStatus = 'pending' | 'verifying' | 'active' | 'failed' | null;

interface DnsRecord {
  record?: string;
  type?: string;
  name?: string;
  value?: string;
  ttl?: number | string;
}

interface SenderState {
  domain: string | null;
  status: SenderStatus;
  records?: DnsRecord[];
  verified_at?: string | null;
  resend_id?: string | null;
}

const POLL_MS = 30_000;

export default function AdminSenderDomainPage() {
  const { org } = useOrganization();
  const [state, setState] = useState<SenderState>({ domain: null, status: null });
  const [loading, setLoading] = useState(true);
  const [input, setInput] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchState = useCallback(async () => {
    if (!org?.id) return;
    try {
      const res = await fetch(`/api/admin/organizations/${org.id}/email-sender`);
      if (res.status === 403) {
        setError('Branded sender domains are a Pro feature.');
        setLoading(false);
        return;
      }
      if (res.ok) {
        const data = (await res.json()) as SenderState;
        setState(data);
      }
    } finally {
      setLoading(false);
    }
  }, [org?.id]);

  useEffect(() => {
    void fetchState();
  }, [fetchState]);

  useEffect(() => {
    if (state.status !== 'pending' && state.status !== 'verifying') return;
    const t = setInterval(fetchState, POLL_MS);
    return () => clearInterval(t);
  }, [state.status, fetchState]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!org?.id) return;
    setSubmitting(true);
    setError(null);
    try {
      const res = await fetch(`/api/admin/organizations/${org.id}/email-sender`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ domain: input.trim().toLowerCase() }),
      });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) {
        setError(body.error || `Request failed (${res.status})`);
        return;
      }
      setState({
        domain: body.domain,
        status: body.status,
        records: body.records,
        resend_id: body.resend_id,
      });
      setInput('');
    } finally {
      setSubmitting(false);
    }
  }

  async function handleVerify() {
    if (!org?.id) return;
    setSubmitting(true);
    setError(null);
    try {
      const res = await fetch(
        `/api/admin/organizations/${org.id}/email-sender/verify`,
        { method: 'POST' },
      );
      const body = await res.json().catch(() => ({}));
      if (!res.ok) setError(body.error || `Verify failed (${res.status})`);
      await fetchState();
    } finally {
      setSubmitting(false);
    }
  }

  async function handleRemove() {
    if (!org?.id) return;
    if (!confirm('Remove this sender domain? Outgoing email will fall back to invites@chesster.io.')) return;
    setSubmitting(true);
    try {
      const res = await fetch(`/api/admin/organizations/${org.id}/email-sender`, {
        method: 'DELETE',
      });
      if (res.ok) setState({ domain: null, status: null });
    } finally {
      setSubmitting(false);
    }
  }

  if (loading) {
    return (
      <div>
        <h1 className="text-2xl font-bold mb-6">Sender domain</h1>
        <p className="text-sm text-gray-500">Loading…</p>
      </div>
    );
  }

  return (
    <div>
      <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100 mb-2">
        Sender domain
      </h1>
      <p className="text-sm text-gray-500 mb-6 max-w-2xl">
        Send invites and notifications from <code>noreply@yourdomain.com</code>{' '}
        instead of the default <code>invites@chesster.io</code>. Pro plan only.
      </p>

      {error && (
        <div className="mb-4 px-4 py-3 rounded-lg border border-red-300 bg-red-50 text-sm text-red-800">
          {error}
        </div>
      )}

      {!state.domain && (
        <form onSubmit={handleSubmit} className="max-w-2xl space-y-4 rounded-xl border border-gray-200 bg-white p-6">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Sender domain
            </label>
            <input
              type="text"
              required
              value={input}
              onChange={e => setInput(e.target.value)}
              placeholder="mail.yourdomain.com"
              className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm font-mono"
            />
          </div>
          <button
            type="submit"
            disabled={submitting || !input.trim()}
            className="px-4 py-2 text-sm font-medium text-white rounded-lg disabled:opacity-50"
            style={{ backgroundColor: 'var(--brand-primary)' }}
          >
            {submitting ? 'Adding…' : 'Add domain'}
          </button>
        </form>
      )}

      {state.domain && state.status !== 'active' && (
        <div className="max-w-3xl rounded-xl border border-yellow-300 bg-yellow-50 p-6">
          <h2 className="text-lg font-semibold mb-1">Awaiting DNS records</h2>
          <p className="text-sm mb-4">
            Add these records to your DNS provider, then click verify. Auto-polls every 30s.
          </p>
          {state.records && state.records.length > 0 && (
            <table className="w-full text-sm font-mono border border-gray-200 rounded">
              <thead className="bg-gray-100">
                <tr>
                  <th className="text-left px-3 py-2">Type</th>
                  <th className="text-left px-3 py-2">Name</th>
                  <th className="text-left px-3 py-2">Value</th>
                </tr>
              </thead>
              <tbody>
                {state.records.map((r, i) => (
                  <tr key={i} className="border-t">
                    <td className="px-3 py-2">{r.type || r.record || '—'}</td>
                    <td className="px-3 py-2">{r.name || '—'}</td>
                    <td className="px-3 py-2 break-all">{r.value || '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          <div className="flex gap-3 mt-5">
            <button
              type="button"
              disabled={submitting}
              onClick={handleVerify}
              className="px-4 py-2 text-sm font-medium text-white rounded-lg disabled:opacity-50"
              style={{ backgroundColor: 'var(--brand-primary)' }}
            >
              {submitting ? 'Verifying…' : 'Verify now'}
            </button>
            <button
              type="button"
              onClick={handleRemove}
              className="px-4 py-2 text-sm font-medium text-red-700 border border-red-300 rounded-lg"
            >
              Remove
            </button>
          </div>
        </div>
      )}

      {state.domain && state.status === 'active' && (
        <div className="max-w-3xl rounded-xl border border-green-300 bg-green-50 p-6">
          <h2 className="text-lg font-semibold mb-1">Active</h2>
          <p className="text-sm">
            Outgoing email now uses <code>{state.domain}</code>.
            {state.verified_at && (
              <span className="text-xs text-gray-500 ml-2">
                Verified {new Date(state.verified_at).toLocaleString()}
              </span>
            )}
          </p>
          <button
            type="button"
            onClick={handleRemove}
            className="mt-5 px-4 py-2 text-sm font-medium text-red-700 border border-red-300 rounded-lg"
          >
            Remove sender domain
          </button>
        </div>
      )}
    </div>
  );
}
