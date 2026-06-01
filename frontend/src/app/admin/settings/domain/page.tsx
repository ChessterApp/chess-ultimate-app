'use client';

import { useCallback, useEffect, useState } from 'react';
import { useOrganization } from '@/contexts/OrganizationContext';

type DomainStatus = 'pending' | 'verifying' | 'active' | 'failed' | null;

interface VerificationRecord {
  type?: string;
  domain?: string;
  value?: string;
  reason?: string;
}

interface DomainState {
  domain: string | null;
  status: DomainStatus;
  verified_at?: string | null;
  verification?: VerificationRecord[];
  vercel_id?: string | null;
}

const POLL_MS = 30_000;

export default function AdminDomainPage() {
  const { org } = useOrganization();
  const [state, setState] = useState<DomainState>({ domain: null, status: null });
  const [loading, setLoading] = useState(true);
  const [input, setInput] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const fetchState = useCallback(async () => {
    if (!org?.id) return;
    try {
      const res = await fetch(`/api/admin/organizations/${org.id}/custom-domain`, {
        headers: { 'X-User-Id': org.id ? '' : '' },
      });
      if (res.ok) {
        const data = (await res.json()) as DomainState;
        setState(data);
      }
    } finally {
      setLoading(false);
    }
  }, [org?.id]);

  useEffect(() => { fetchState(); }, [fetchState]);

  // Auto-poll while pending/verifying so the UI flips to "active" without a reload.
  useEffect(() => {
    if (state.status !== 'pending' && state.status !== 'verifying') return;
    const t = setInterval(fetchState, POLL_MS);
    return () => clearInterval(t);
  }, [state.status, fetchState]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!org?.id) return;
    setSubmitting(true);
    setErrorMsg(null);
    try {
      const res = await fetch(`/api/admin/organizations/${org.id}/custom-domain`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ domain: input.trim().toLowerCase() }),
      });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) {
        setErrorMsg(body.error || `Request failed (${res.status})`);
        return;
      }
      setState({
        domain: body.domain,
        status: body.status,
        verification: body.verification,
        vercel_id: body.vercel_id,
      });
      setInput('');
    } finally {
      setSubmitting(false);
    }
  }

  async function handleVerify() {
    if (!org?.id) return;
    setSubmitting(true);
    setErrorMsg(null);
    try {
      const res = await fetch(
        `/api/admin/organizations/${org.id}/custom-domain/verify`,
        { method: 'POST' },
      );
      const body = await res.json().catch(() => ({}));
      if (!res.ok) {
        setErrorMsg(body.error || `Verify failed (${res.status})`);
      }
      await fetchState();
    } finally {
      setSubmitting(false);
    }
  }

  async function handleRemove() {
    if (!org?.id) return;
    if (!confirm('Remove this custom domain? Your school will fall back to the chesster.io subdomain.')) {
      return;
    }
    setSubmitting(true);
    setErrorMsg(null);
    try {
      const res = await fetch(`/api/admin/organizations/${org.id}/custom-domain`, {
        method: 'DELETE',
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        setErrorMsg(body.error || `Remove failed (${res.status})`);
      } else {
        setState({ domain: null, status: null });
      }
    } finally {
      setSubmitting(false);
    }
  }

  if (loading) {
    return (
      <div>
        <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100 mb-6">Custom Domain</h1>
        <p className="text-sm text-gray-500">Loading…</p>
      </div>
    );
  }

  return (
    <div>
      <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100 mb-2">Custom Domain</h1>
      <p className="text-sm text-gray-500 dark:text-gray-400 mb-6 max-w-2xl">
        Bring your own domain (e.g. <code>chess.yourschool.com</code>) to replace the
        default <code>{org?.slug ?? 'your-school'}.chesster.io</code> URL. Available on
        paid plans.
      </p>

      {errorMsg && (
        <div className="mb-4 px-4 py-3 rounded-lg border border-red-300 bg-red-50 dark:bg-red-900/20 text-sm text-red-800 dark:text-red-200">
          {errorMsg}
        </div>
      )}

      {/* State 1: No domain configured */}
      {!state.domain && (
        <form onSubmit={handleSubmit} className="max-w-2xl space-y-4 rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 p-6">
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              Domain
            </label>
            <input
              type="text"
              required
              value={input}
              onChange={e => setInput(e.target.value)}
              placeholder="chess.yourschool.com"
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-sm font-mono"
            />
            <p className="text-xs text-gray-500 mt-2">
              Lowercase, no protocol, no trailing dot. Subdomains of chesster.io are not allowed.
            </p>
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

      {/* State 2: Pending verification */}
      {state.domain && state.status === 'pending' && (
        <div className="max-w-3xl rounded-xl border border-yellow-300 dark:border-yellow-700 bg-yellow-50 dark:bg-yellow-900/10 p-6">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-1">
            Awaiting DNS records
          </h2>
          <p className="text-sm text-gray-700 dark:text-gray-300 mb-4">
            Add the following records to your DNS provider for <code className="font-mono">{state.domain}</code>, then click verify.
          </p>
          <table className="w-full text-sm font-mono border border-gray-200 dark:border-gray-700 rounded">
            <thead className="bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-200">
              <tr>
                <th className="text-left px-3 py-2">Type</th>
                <th className="text-left px-3 py-2">Name</th>
                <th className="text-left px-3 py-2">Value</th>
              </tr>
            </thead>
            <tbody>
              {(state.verification && state.verification.length > 0)
                ? state.verification.map((rec, i) => (
                    <tr key={i} className="border-t border-gray-200 dark:border-gray-700">
                      <td className="px-3 py-2">{rec.type || '—'}</td>
                      <td className="px-3 py-2">{rec.domain || '—'}</td>
                      <td className="px-3 py-2 break-all">{rec.value || '—'}</td>
                    </tr>
                  ))
                : (
                  <tr>
                    <td colSpan={3} className="px-3 py-3 text-gray-500">
                      DNS instructions will appear here once Vercel returns them. Click verify to refresh.
                    </td>
                  </tr>
                )}
            </tbody>
          </table>
          <div className="flex gap-3 mt-5">
            <button
              type="button"
              disabled={submitting}
              onClick={handleVerify}
              className="px-4 py-2 text-sm font-medium text-white rounded-lg disabled:opacity-50"
              style={{ backgroundColor: 'var(--brand-primary)' }}
            >
              {submitting ? 'Verifying…' : 'I added the records — verify now'}
            </button>
            <button
              type="button"
              disabled={submitting}
              onClick={handleRemove}
              className="px-4 py-2 text-sm font-medium text-red-700 dark:text-red-300 border border-red-300 dark:border-red-700 rounded-lg"
            >
              Cancel
            </button>
          </div>
          <p className="text-xs text-gray-500 mt-3">Status is auto-checked every 30 seconds.</p>
        </div>
      )}

      {/* State 3: Active */}
      {state.domain && state.status === 'active' && (
        <div className="max-w-3xl rounded-xl border border-green-300 dark:border-green-700 bg-green-50 dark:bg-green-900/10 p-6">
          <div className="flex items-center gap-2 mb-2">
            <span className="text-green-700 dark:text-green-300 text-xl">✓</span>
            <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
              Active
            </h2>
          </div>
          <p className="text-sm text-gray-700 dark:text-gray-300 mb-1">
            Your school is live at{' '}
            <a
              href={`https://${state.domain}`}
              target="_blank" rel="noreferrer"
              className="font-mono underline"
            >
              https://{state.domain}
            </a>
          </p>
          {state.verified_at && (
            <p className="text-xs text-gray-500 dark:text-gray-400">
              Verified {new Date(state.verified_at).toLocaleString()}
            </p>
          )}
          <button
            type="button"
            disabled={submitting}
            onClick={handleRemove}
            className="mt-5 px-4 py-2 text-sm font-medium text-red-700 dark:text-red-300 border border-red-300 dark:border-red-700 rounded-lg disabled:opacity-50"
          >
            Remove custom domain
          </button>
        </div>
      )}

      {/* State 4: Failed */}
      {state.domain && state.status === 'failed' && (
        <div className="max-w-3xl rounded-xl border border-red-300 dark:border-red-700 bg-red-50 dark:bg-red-900/10 p-6">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-2">
            Verification failed
          </h2>
          <p className="text-sm text-gray-700 dark:text-gray-300 mb-4">
            Vercel could not verify <code className="font-mono">{state.domain}</code>. Double-check
            your DNS records, wait a few minutes for propagation, then retry.
          </p>
          <div className="flex gap-3">
            <button
              type="button"
              disabled={submitting}
              onClick={handleVerify}
              className="px-4 py-2 text-sm font-medium text-white rounded-lg disabled:opacity-50"
              style={{ backgroundColor: 'var(--brand-primary)' }}
            >
              {submitting ? 'Retrying…' : 'Retry verification'}
            </button>
            <button
              type="button"
              disabled={submitting}
              onClick={handleRemove}
              className="px-4 py-2 text-sm font-medium text-red-700 dark:text-red-300 border border-red-300 dark:border-red-700 rounded-lg"
            >
              Remove
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
