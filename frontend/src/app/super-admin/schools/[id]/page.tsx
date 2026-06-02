'use client';

import { useAuth } from '@clerk/nextjs';
import Link from 'next/link';
import { useParams } from 'next/navigation';
import { useCallback, useEffect, useState } from 'react';

interface Organization {
  id: string;
  slug: string;
  name: string;
  status: 'active' | 'suspended' | 'trial' | string;
  custom_domain?: string | null;
  custom_domain_status?: string | null;
  contact_email?: string | null;
  created_at?: string | null;
  clerk_org_id?: string | null;
}

interface Billing {
  plan?: string | null;
  student_count?: number | null;
  billing_cycle?: string | null;
  next_invoice_at?: string | null;
}

interface Member {
  id: string;
  user_id: string;
  role: 'owner' | 'admin' | 'teacher' | 'student' | string;
  joined_at?: string | null;
  email?: string | null;
}

interface AuditEntry {
  id: string;
  action: string;
  payload: Record<string, unknown> | null;
  created_at: string;
  admin_clerk_id: string;
}

interface DetailResponse {
  organization: Organization;
  billing: Billing | null;
  members: Member[];
  audit: AuditEntry[];
}

type ActionState = 'idle' | 'pending' | 'error';
type TabKey = 'overview' | 'members' | 'audit';

export default function SuperAdminSchoolDetailPage() {
  const params = useParams<{ id: string }>();
  const orgId = params?.id;
  const { getToken } = useAuth();

  const [data, setData] = useState<DetailResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionState, setActionState] = useState<ActionState>('idle');
  const [feedback, setFeedback] = useState<string | null>(null);
  const [tab, setTab] = useState<TabKey>('overview');

  const [suspendOpen, setSuspendOpen] = useState(false);
  const [suspendReason, setSuspendReason] = useState('');

  const [unsuspendOpen, setUnsuspendOpen] = useState(false);
  const [unsuspendReason, setUnsuspendReason] = useState('');

  const [promoteOpen, setPromoteOpen] = useState(false);
  const [promoteUserId, setPromoteUserId] = useState<string | null>(null);
  const [promoteReason, setPromoteReason] = useState('');

  const [clerkSyncing, setClerkSyncing] = useState(false);

  const fetchDetail = useCallback(async () => {
    if (!orgId) return;
    setLoading(true);
    setError(null);
    try {
      const token = await getToken();
      const res = await fetch(`/api/super-admin/organizations/${orgId}`, {
        credentials: 'include',
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (res.status === 404) {
        throw new Error('Organization not found');
      }
      if (!res.ok) throw new Error(`Failed to load (${res.status})`);
      setData(await res.json());
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Load failed');
    } finally {
      setLoading(false);
    }
  }, [orgId, getToken]);

  useEffect(() => {
    fetchDetail();
  }, [fetchDetail]);

  const callAction = useCallback(
    async (path: string, body?: Record<string, unknown>) => {
      setActionState('pending');
      setFeedback(null);
      try {
        const token = await getToken();
        const res = await fetch(`/api/super-admin/organizations/${orgId}${path}`, {
          method: 'POST',
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
    [orgId, getToken],
  );

  const handleSuspend = async () => {
    if (suspendReason.trim().length < 3) return;
    const result = await callAction('/suspend', { reason: suspendReason.trim() });
    if (!result) return;
    setSuspendOpen(false);
    setSuspendReason('');
    setFeedback('Organization suspended.');
    fetchDetail();
  };

  const handleUnsuspend = async () => {
    if (unsuspendReason.trim().length < 3) return;
    const result = await callAction('/unsuspend', { reason: unsuspendReason.trim() });
    if (!result) return;
    setUnsuspendOpen(false);
    setUnsuspendReason('');
    setFeedback('Organization reactivated.');
    fetchDetail();
  };

  const handlePromote = async () => {
    if (!promoteUserId || promoteReason.trim().length < 3) return;
    const result = await callAction('/promote', {
      user_id: promoteUserId,
      reason: promoteReason.trim(),
    });
    if (!result) return;
    setPromoteOpen(false);
    setPromoteReason('');
    setPromoteUserId(null);
    setFeedback('Member promoted to owner.');
    fetchDetail();
  };

  const handleClerkSync = async () => {
    if (!orgId) return;
    setClerkSyncing(true);
    setFeedback(null);
    try {
      const token = await getToken();
      const res = await fetch(`/api/super-admin/schools/${orgId}/sync-clerk`, {
        method: 'POST',
        credentials: 'include',
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      const payload = await res.json().catch(() => ({}));
      if (!res.ok) {
        setFeedback(payload?.error || `Clerk sync failed (${res.status})`);
        return;
      }
      if (payload?.already_synced) {
        setFeedback('Already synced to Clerk.');
      } else {
        const failed = Array.isArray(payload?.failed_memberships) ? payload.failed_memberships.length : 0;
        setFeedback(
          failed > 0
            ? `Synced org; ${failed} membership(s) failed — retry to backfill.`
            : 'Synced to Clerk.'
        );
      }
      fetchDetail();
    } catch (err) {
      setFeedback(err instanceof Error ? err.message : 'Clerk sync failed');
    } finally {
      setClerkSyncing(false);
    }
  };

  if (!orgId) return null;

  if (loading) {
    return <div className="text-gray-500">Loading organization…</div>;
  }
  if (error) {
    return (
      <div className="space-y-4">
        <Link href="/super-admin/schools" className="text-sm text-blue-600 hover:underline">
          ← Back to schools
        </Link>
        <div className="text-red-600">{error}</div>
      </div>
    );
  }
  if (!data) return null;

  const org = data.organization;
  const isSuspended = org.status === 'suspended';

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <Link href="/super-admin/schools" className="text-sm text-blue-600 hover:underline">
            ← Back to schools
          </Link>
          <h1 className="mt-2 text-2xl font-bold text-gray-900 dark:text-gray-100">
            {org.name}
          </h1>
          <p className="text-sm text-gray-500">
            <span className="font-mono">{org.slug}</span> · id:{org.id}
          </p>
          <div className="mt-2 flex items-center gap-2">
            <ClerkSyncBadge clerkOrgId={org.clerk_org_id} />
            {!org.clerk_org_id && (
              <button
                type="button"
                onClick={handleClerkSync}
                disabled={clerkSyncing}
                className="rounded-md border border-blue-600 px-2 py-0.5 text-xs font-medium text-blue-700 hover:bg-blue-50 dark:hover:bg-blue-900/20 disabled:opacity-60"
              >
                {clerkSyncing ? 'Syncing…' : 'Sync to Clerk'}
              </button>
            )}
          </div>
        </div>
        <StatusBadge status={org.status} />
      </div>

      {feedback && (
        <div className="rounded-md border border-blue-200 bg-blue-50 dark:bg-blue-900/20 px-3 py-2 text-sm text-blue-800 dark:text-blue-200">
          {feedback}
        </div>
      )}

      <section className="rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 p-4">
        <h2 className="text-base font-semibold text-gray-900 dark:text-gray-100">Actions</h2>
        <p className="text-xs text-gray-500 mb-3">
          Every action is recorded in the audit log with reason and admin id.
        </p>
        <div className="flex flex-wrap gap-2">
          {isSuspended ? (
            <button
              type="button"
              onClick={() => setUnsuspendOpen(true)}
              className="rounded-md bg-green-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-green-700"
            >
              Unsuspend
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
            onClick={() => {
              setPromoteUserId(null);
              setPromoteReason('');
              setPromoteOpen(true);
            }}
            className="rounded-md border border-blue-600 px-3 py-1.5 text-sm font-medium text-blue-700 hover:bg-blue-50 dark:hover:bg-blue-900/20"
          >
            Promote owner
          </button>
        </div>
      </section>

      <div className="border-b border-gray-200 dark:border-gray-700">
        <nav className="flex gap-4">
          {(['overview', 'members', 'audit'] as TabKey[]).map((key) => (
            <button
              key={key}
              type="button"
              onClick={() => setTab(key)}
              className={`px-1 py-2 text-sm font-medium capitalize border-b-2 transition-colors ${
                tab === key
                  ? 'border-blue-600 text-blue-700 dark:text-blue-300'
                  : 'border-transparent text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-200'
              }`}
            >
              {key}
            </button>
          ))}
        </nav>
      </div>

      {tab === 'overview' && (
        <section className="grid md:grid-cols-2 gap-4">
          <Card title="Organization">
            <Row label="Status" value={org.status} />
            <Row label="Slug" value={org.slug} />
            <Row label="Contact" value={org.contact_email || '—'} />
            <Row
              label="Created"
              value={org.created_at ? new Date(org.created_at).toLocaleString() : '—'}
            />
          </Card>

          <Card title="Custom domain">
            <Row label="Domain" value={org.custom_domain || '—'} />
            <Row label="Status" value={org.custom_domain_status || '—'} />
          </Card>

          <Card title="Billing">
            <Row label="Plan" value={data.billing?.plan || '—'} />
            <Row label="Students" value={data.billing?.student_count ?? '—'} />
            <Row label="Cycle" value={data.billing?.billing_cycle || '—'} />
            <Row
              label="Next invoice"
              value={
                data.billing?.next_invoice_at
                  ? new Date(data.billing.next_invoice_at).toLocaleDateString()
                  : '—'
              }
            />
          </Card>

          <Card title="Membership totals">
            <Row label="Members" value={data.members.length} />
            <Row
              label="Owners"
              value={data.members.filter((m) => m.role === 'owner').length}
            />
            <Row
              label="Teachers"
              value={data.members.filter((m) => m.role === 'teacher').length}
            />
            <Row
              label="Students"
              value={data.members.filter((m) => m.role === 'student').length}
            />
          </Card>
        </section>
      )}

      {tab === 'members' && (
        <section className="overflow-x-auto rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800">
          <table className="min-w-full text-sm">
            <thead className="bg-gray-50 dark:bg-gray-900/50">
              <tr>
                <Th>Email</Th>
                <Th>User id</Th>
                <Th>Role</Th>
                <Th>Joined</Th>
                <Th />
              </tr>
            </thead>
            <tbody>
              {data.members.length === 0 && (
                <tr>
                  <td colSpan={5} className="px-4 py-6 text-center text-gray-500">
                    No members yet.
                  </td>
                </tr>
              )}
              {data.members.map((m) => (
                <tr
                  key={m.id}
                  className="border-t border-gray-100 dark:border-gray-700/50"
                >
                  <Td>{m.email || '—'}</Td>
                  <Td>
                    <span className="font-mono text-xs">{m.user_id}</span>
                  </Td>
                  <Td>
                    <RoleBadge role={m.role} />
                  </Td>
                  <Td>
                    {m.joined_at ? new Date(m.joined_at).toLocaleDateString() : '—'}
                  </Td>
                  <Td>
                    {m.role !== 'owner' && (
                      <button
                        type="button"
                        onClick={() => {
                          setPromoteUserId(m.user_id);
                          setPromoteReason('');
                          setPromoteOpen(true);
                        }}
                        className="text-blue-600 hover:underline text-xs"
                      >
                        Promote →
                      </button>
                    )}
                  </Td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}

      {tab === 'audit' && (
        <section className="rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 p-4">
          {data.audit.length === 0 && (
            <p className="text-sm text-gray-500">No audit entries yet.</p>
          )}
          <ul className="space-y-2">
            {data.audit.map((entry) => (
              <li key={entry.id} className="text-sm border-b border-gray-100 dark:border-gray-700/50 pb-2">
                <div className="flex flex-wrap gap-2 items-baseline">
                  <span className="font-mono text-xs text-gray-500">
                    {new Date(entry.created_at).toLocaleString()}
                  </span>
                  <span className="font-medium text-gray-900 dark:text-gray-100">
                    {entry.action}
                  </span>
                  <span className="text-xs text-gray-500">by {entry.admin_clerk_id}</span>
                </div>
                {entry.payload && Object.keys(entry.payload).length > 0 && (
                  <pre className="mt-1 text-xs text-gray-600 dark:text-gray-400 whitespace-pre-wrap font-mono">
                    {JSON.stringify(entry.payload, null, 2)}
                  </pre>
                )}
              </li>
            ))}
          </ul>
        </section>
      )}

      {suspendOpen && (
        <Modal title="Suspend organization" onClose={() => setSuspendOpen(false)}>
          <p className="text-sm text-gray-600 dark:text-gray-400 mb-3">
            The organization will be marked suspended. Required: a reason for the audit log.
          </p>
          <textarea
            value={suspendReason}
            onChange={(e) => setSuspendReason(e.target.value)}
            placeholder="Reason (min 3 chars)"
            className="w-full rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-900 px-3 py-2 text-sm"
            rows={3}
          />
          <ModalActions
            onCancel={() => setSuspendOpen(false)}
            onConfirm={handleSuspend}
            confirmLabel="Confirm suspend"
            confirmTone="warning"
            disabled={suspendReason.trim().length < 3 || actionState === 'pending'}
          />
        </Modal>
      )}

      {unsuspendOpen && (
        <Modal title="Unsuspend organization" onClose={() => setUnsuspendOpen(false)}>
          <p className="text-sm text-gray-600 dark:text-gray-400 mb-3">
            The organization will be marked active again. Required: a reason for the audit log.
          </p>
          <textarea
            value={unsuspendReason}
            onChange={(e) => setUnsuspendReason(e.target.value)}
            placeholder="Reason (min 3 chars)"
            className="w-full rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-900 px-3 py-2 text-sm"
            rows={3}
          />
          <ModalActions
            onCancel={() => setUnsuspendOpen(false)}
            onConfirm={handleUnsuspend}
            confirmLabel="Confirm unsuspend"
            confirmTone="success"
            disabled={unsuspendReason.trim().length < 3 || actionState === 'pending'}
          />
        </Modal>
      )}

      {promoteOpen && (
        <Modal title="Promote member to owner" onClose={() => setPromoteOpen(false)}>
          <p className="text-sm text-gray-600 dark:text-gray-400 mb-3">
            Multiple owners are allowed; the existing owner is not demoted.
          </p>
          <label className="block text-xs font-medium text-gray-600 dark:text-gray-400">
            Member
          </label>
          <select
            value={promoteUserId || ''}
            onChange={(e) => setPromoteUserId(e.target.value || null)}
            className="mt-1 w-full rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-900 px-3 py-2 text-sm"
          >
            <option value="">Select a member…</option>
            {data.members
              .filter((m) => m.role !== 'owner')
              .map((m) => (
                <option key={m.user_id} value={m.user_id}>
                  {m.email || m.user_id} ({m.role})
                </option>
              ))}
          </select>
          <label className="mt-3 block text-xs font-medium text-gray-600 dark:text-gray-400">
            Reason
          </label>
          <textarea
            value={promoteReason}
            onChange={(e) => setPromoteReason(e.target.value)}
            placeholder="Reason (min 3 chars)"
            className="mt-1 w-full rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-900 px-3 py-2 text-sm"
            rows={3}
          />
          <ModalActions
            onCancel={() => setPromoteOpen(false)}
            onConfirm={handlePromote}
            confirmLabel="Confirm promote"
            confirmTone="primary"
            disabled={
              !promoteUserId ||
              promoteReason.trim().length < 3 ||
              actionState === 'pending'
            }
          />
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

function Th({ children }: { children?: React.ReactNode }) {
  return (
    <th className="px-4 py-2 text-left text-xs font-semibold uppercase tracking-wide text-gray-500">
      {children}
    </th>
  );
}

function Td({ children }: { children?: React.ReactNode }) {
  return <td className="px-4 py-3 text-gray-800 dark:text-gray-200">{children}</td>;
}

function StatusBadge({ status }: { status: string }) {
  const tone =
    status === 'suspended'
      ? 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-200'
      : status === 'trial'
      ? 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-200'
      : 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-200';
  return (
    <span className={`rounded-full px-3 py-1 text-xs font-semibold ${tone}`}>{status}</span>
  );
}

function ClerkSyncBadge({ clerkOrgId }: { clerkOrgId: string | null | undefined }) {
  if (clerkOrgId) {
    return (
      <span
        className="inline-block rounded px-2 py-0.5 text-xs font-medium bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-200"
        title={clerkOrgId}
      >
        Clerk: synced ({clerkOrgId})
      </span>
    );
  }
  return (
    <span className="inline-block rounded px-2 py-0.5 text-xs font-medium bg-gray-200 text-gray-700 dark:bg-gray-700 dark:text-gray-300">
      Clerk: not synced
    </span>
  );
}

function RoleBadge({ role }: { role: string }) {
  const tone =
    role === 'owner'
      ? 'bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-200'
      : role === 'admin'
      ? 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-200'
      : role === 'teacher'
      ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-200'
      : 'bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300';
  return (
    <span className={`inline-block rounded px-2 py-0.5 text-xs font-medium ${tone}`}>
      {role}
    </span>
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

function ModalActions({
  onCancel,
  onConfirm,
  confirmLabel,
  confirmTone,
  disabled,
}: {
  onCancel: () => void;
  onConfirm: () => void;
  confirmLabel: string;
  confirmTone: 'primary' | 'warning' | 'success';
  disabled: boolean;
}) {
  const tone =
    confirmTone === 'warning'
      ? 'bg-yellow-600 hover:bg-yellow-700'
      : confirmTone === 'success'
      ? 'bg-green-600 hover:bg-green-700'
      : 'bg-blue-600 hover:bg-blue-700';
  return (
    <div className="mt-3 flex justify-end gap-2">
      <button
        type="button"
        onClick={onCancel}
        className="rounded-md border border-gray-300 dark:border-gray-600 px-3 py-1.5 text-sm"
      >
        Cancel
      </button>
      <button
        type="button"
        disabled={disabled}
        onClick={onConfirm}
        className={`rounded-md px-3 py-1.5 text-sm font-medium text-white disabled:opacity-60 ${tone}`}
      >
        {confirmLabel}
      </button>
    </div>
  );
}
