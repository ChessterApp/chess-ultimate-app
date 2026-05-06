'use client';

import { useAuth } from '@clerk/nextjs';
import Link from 'next/link';
import { useParams, useRouter } from 'next/navigation';
import { useCallback, useEffect, useState } from 'react';

interface UserDetail {
  clerk_id: string;
  cache: {
    email?: string;
    name?: string | null;
    signup_at?: string | null;
    last_seen_at?: string | null;
    subscription_status?: string | null;
    whop_membership_id?: string | null;
    org_count?: number | null;
    total_revenue_cents?: number | null;
  } | null;
  status: {
    status?: string;
    suspended_reason?: string | null;
    suspended_at?: string | null;
    suspended_by?: string | null;
    notes?: string | null;
  } | null;
  memberships: Array<{
    id: string;
    organization_id: string;
    role: string;
    joined_at?: string;
  }>;
  audit: Array<{
    id: string;
    action: string;
    payload: Record<string, unknown> | null;
    created_at: string;
    admin_clerk_id: string;
  }>;
  clerk: Record<string, unknown> | null;
}

type ActionState = 'idle' | 'pending' | 'error';

export default function SuperAdminUserDetailPage() {
  const params = useParams<{ clerkId: string }>();
  const clerkId = params?.clerkId;
  const router = useRouter();
  const { getToken } = useAuth();

  const [data, setData] = useState<UserDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionState, setActionState] = useState<ActionState>('idle');
  const [refundOpen, setRefundOpen] = useState(false);
  const [refundReason, setRefundReason] = useState('');
  const [refundAmount, setRefundAmount] = useState('');
  const [suspendOpen, setSuspendOpen] = useState(false);
  const [suspendReason, setSuspendReason] = useState('');
  const [feedback, setFeedback] = useState<string | null>(null);

  const fetchDetail = useCallback(async () => {
    if (!clerkId) return;
    setLoading(true);
    setError(null);
    try {
      const token = await getToken();
      const res = await fetch(`/api/super-admin/users/${clerkId}`, {
        credentials: 'include',
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!res.ok) throw new Error(`Failed to load user (${res.status})`);
      setData(await res.json());
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Load failed');
    } finally {
      setLoading(false);
    }
  }, [clerkId, getToken]);

  useEffect(() => {
    fetchDetail();
  }, [fetchDetail]);

  const callAction = useCallback(
    async (path: string, body?: Record<string, unknown>, method: 'POST' | 'DELETE' = 'POST') => {
      setActionState('pending');
      setFeedback(null);
      try {
        const token = await getToken();
        const res = await fetch(`/api/super-admin/users/${clerkId}${path}`, {
          method,
          credentials: 'include',
          headers: {
            'Content-Type': 'application/json',
            ...(token ? { Authorization: `Bearer ${token}` } : {}),
          },
          body: body ? JSON.stringify(body) : undefined,
        });
        const payload = await res.json().catch(() => ({}));
        if (!res.ok) {
          setActionState('error');
          setFeedback(payload?.error || `Request failed (${res.status})`);
          return null;
        }
        setActionState('idle');
        return payload;
      } catch (err) {
        setActionState('error');
        setFeedback(err instanceof Error ? err.message : 'Request failed');
        return null;
      }
    },
    [clerkId, getToken],
  );

  const handleSuspend = async () => {
    if (!suspendReason.trim()) return;
    // Optimistic update
    setData((prev) =>
      prev ? { ...prev, status: { ...prev.status, status: 'suspended', suspended_reason: suspendReason } } : prev,
    );
    const result = await callAction('/suspend', { reason: suspendReason });
    if (!result) {
      // Revert on error
      fetchDetail();
      return;
    }
    setSuspendOpen(false);
    setSuspendReason('');
    setFeedback('User suspended.');
    fetchDetail();
  };

  const handleUnsuspend = async () => {
    setData((prev) =>
      prev ? { ...prev, status: { ...prev.status, status: 'active', suspended_reason: null } } : prev,
    );
    const result = await callAction('/unsuspend');
    if (!result) {
      fetchDetail();
      return;
    }
    setFeedback('User reactivated.');
    fetchDetail();
  };

  const handleRefund = async () => {
    if (!refundReason.trim()) return;
    const body: Record<string, unknown> = { reason: refundReason };
    if (refundAmount.trim()) body.amount_cents = Number(refundAmount.trim());
    const result = await callAction('/refund', body);
    if (!result) return;
    setRefundOpen(false);
    setRefundReason('');
    setRefundAmount('');
    setFeedback('Refund issued.');
    fetchDetail();
  };

  const handleImpersonate = async () => {
    if (!clerkId) return;
    const result = await callAction('/impersonate', { reason: 'support' });
    if (!result) return;
    // Cookie was set server-side; navigate to the user's dashboard.
    router.push('/dashboard');
  };

  if (!clerkId) return null;

  if (loading) {
    return <div className="text-gray-500">Loading user…</div>;
  }
  if (error) {
    return <div className="text-red-600">{error}</div>;
  }
  if (!data) return null;

  const isSuspended = data.status?.status === 'suspended';

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <Link href="/super-admin/users" className="text-sm text-blue-600 hover:underline">
            ← Back to users
          </Link>
          <h1 className="mt-2 text-2xl font-bold text-gray-900 dark:text-gray-100">
            {data.cache?.email || data.clerk_id}
          </h1>
          <p className="text-sm text-gray-500">
            {data.cache?.name || '—'} · clerk:{data.clerk_id}
          </p>
        </div>
        <span
          className={`rounded-full px-3 py-1 text-xs font-semibold ${
            isSuspended
              ? 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-200'
              : 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-200'
          }`}
        >
          {data.status?.status || 'active'}
        </span>
      </div>

      {feedback && (
        <div className="rounded-md border border-blue-200 bg-blue-50 dark:bg-blue-900/20 px-3 py-2 text-sm text-blue-800 dark:text-blue-200">
          {feedback}
        </div>
      )}

      <section className="grid md:grid-cols-2 gap-4">
        <Card title="Subscription">
          <Row label="Plan" value={data.cache?.subscription_status || 'free'} />
          <Row label="Whop membership" value={data.cache?.whop_membership_id || '—'} />
          <Row
            label="Lifetime revenue"
            value={
              data.cache?.total_revenue_cents != null
                ? `$${(data.cache.total_revenue_cents / 100).toFixed(2)}`
                : '—'
            }
          />
          <Row
            label="Signed up"
            value={data.cache?.signup_at ? new Date(data.cache.signup_at).toLocaleString() : '—'}
          />
          <Row
            label="Last seen"
            value={data.cache?.last_seen_at ? new Date(data.cache.last_seen_at).toLocaleString() : '—'}
          />
        </Card>

        <Card title="Status">
          <Row label="Account" value={data.status?.status || 'active'} />
          <Row label="Reason" value={data.status?.suspended_reason || '—'} />
          <Row
            label="Suspended at"
            value={data.status?.suspended_at ? new Date(data.status.suspended_at).toLocaleString() : '—'}
          />
          <Row label="Suspended by" value={data.status?.suspended_by || '—'} />
        </Card>

        <Card title="Org memberships">
          {data.memberships.length === 0 && <p className="text-sm text-gray-500">None.</p>}
          {data.memberships.map((m) => (
            <Row key={m.id} label={m.role} value={`org:${m.organization_id}`} />
          ))}
        </Card>

        <Card title="Recent activity">
          {data.audit.length === 0 && <p className="text-sm text-gray-500">No actions yet.</p>}
          <ul className="space-y-2">
            {data.audit.map((entry) => (
              <li key={entry.id} className="text-sm">
                <span className="font-mono text-xs text-gray-500">
                  {new Date(entry.created_at).toLocaleString()}
                </span>{' '}
                <span className="font-medium text-gray-900 dark:text-gray-100">{entry.action}</span>{' '}
                <span className="text-xs text-gray-500">by {entry.admin_clerk_id}</span>
              </li>
            ))}
          </ul>
        </Card>
      </section>

      <section className="rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 p-4">
        <h2 className="text-base font-semibold text-gray-900 dark:text-gray-100">Actions</h2>
        <p className="text-xs text-gray-500 mb-3">
          Every action is recorded in the audit log with reason and admin id.
        </p>
        <div className="flex flex-wrap gap-2">
          {isSuspended ? (
            <button
              type="button"
              disabled={actionState === 'pending'}
              onClick={handleUnsuspend}
              className="rounded-md bg-green-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-green-700 disabled:opacity-60"
            >
              Reactivate
            </button>
          ) : (
            <button
              type="button"
              onClick={() => setSuspendOpen(true)}
              className="rounded-md bg-yellow-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-yellow-700"
            >
              Suspend
            </button>
          )}
          <button
            type="button"
            onClick={() => setRefundOpen(true)}
            className="rounded-md bg-red-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-red-700"
          >
            Refund
          </button>
          <button
            type="button"
            disabled={actionState === 'pending'}
            onClick={handleImpersonate}
            className="rounded-md border border-blue-600 px-3 py-1.5 text-sm font-medium text-blue-700 hover:bg-blue-50 dark:hover:bg-blue-900/20 disabled:opacity-60"
          >
            View as user (read-only)
          </button>
        </div>
      </section>

      {suspendOpen && (
        <Modal title="Suspend user" onClose={() => setSuspendOpen(false)}>
          <p className="text-sm text-gray-600 dark:text-gray-400 mb-3">
            The user will be unable to sign in. Required: a reason for the audit log.
          </p>
          <textarea
            value={suspendReason}
            onChange={(e) => setSuspendReason(e.target.value)}
            placeholder="Reason"
            className="w-full rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-900 px-3 py-2 text-sm"
            rows={3}
          />
          <div className="mt-3 flex justify-end gap-2">
            <button
              type="button"
              onClick={() => setSuspendOpen(false)}
              className="rounded-md border border-gray-300 dark:border-gray-600 px-3 py-1.5 text-sm"
            >
              Cancel
            </button>
            <button
              type="button"
              disabled={!suspendReason.trim() || actionState === 'pending'}
              onClick={handleSuspend}
              className="rounded-md bg-yellow-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-yellow-700 disabled:opacity-60"
            >
              Confirm suspend
            </button>
          </div>
        </Modal>
      )}

      {refundOpen && (
        <Modal title="Issue refund" onClose={() => setRefundOpen(false)}>
          <p className="text-sm text-gray-600 dark:text-gray-400 mb-3">
            Issues a Whop refund. Leave amount blank for a full refund.
          </p>
          <label className="block text-xs font-medium text-gray-600 dark:text-gray-400">Reason</label>
          <textarea
            value={refundReason}
            onChange={(e) => setRefundReason(e.target.value)}
            className="mt-1 w-full rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-900 px-3 py-2 text-sm"
            rows={3}
          />
          <label className="mt-3 block text-xs font-medium text-gray-600 dark:text-gray-400">
            Amount (cents, optional)
          </label>
          <input
            value={refundAmount}
            onChange={(e) => setRefundAmount(e.target.value.replace(/[^0-9]/g, ''))}
            inputMode="numeric"
            className="mt-1 w-full rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-900 px-3 py-2 text-sm"
            placeholder="e.g. 999"
          />
          <div className="mt-3 flex justify-end gap-2">
            <button
              type="button"
              onClick={() => setRefundOpen(false)}
              className="rounded-md border border-gray-300 dark:border-gray-600 px-3 py-1.5 text-sm"
            >
              Cancel
            </button>
            <button
              type="button"
              disabled={!refundReason.trim() || actionState === 'pending'}
              onClick={handleRefund}
              className="rounded-md bg-red-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-red-700 disabled:opacity-60"
            >
              Confirm refund
            </button>
          </div>
        </Modal>
      )}
    </div>
  );
}

function Card({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 p-4">
      <h3 className="text-sm font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">
        {title}
      </h3>
      <div className="mt-2 space-y-1">{children}</div>
    </div>
  );
}

function Row({ label, value }: { label: string; value: string | number | null | undefined }) {
  return (
    <div className="flex justify-between gap-2 text-sm">
      <span className="text-gray-500 dark:text-gray-400">{label}</span>
      <span className="text-gray-900 dark:text-gray-100 font-mono text-xs">{value ?? '—'}</span>
    </div>
  );
}

function Modal({
  title,
  children,
  onClose,
}: {
  title: string;
  children: React.ReactNode;
  onClose: () => void;
}) {
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      onClick={onClose}
    >
      <div
        className="w-full max-w-md rounded-lg bg-white dark:bg-gray-800 p-5 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="text-base font-semibold text-gray-900 dark:text-gray-100">{title}</h2>
        <div className="mt-3">{children}</div>
      </div>
    </div>
  );
}
