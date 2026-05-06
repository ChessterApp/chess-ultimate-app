'use client';

import { useAuth } from '@clerk/nextjs';
import Link from 'next/link';
import { useEffect, useMemo, useRef, useState } from 'react';

interface UserRow {
  clerk_id: string;
  email: string;
  name: string | null;
  signup_at: string | null;
  subscription_status: string | null;
  account_status?: string | null;
  org_count?: number | null;
}

const PLAN_OPTIONS = ['', 'free', 'weekly', 'monthly', 'yearly', 'cancelled'];
const STATUS_OPTIONS = ['', 'active', 'suspended', 'banned', 'deleted'];

export default function SuperAdminUsersPage() {
  const { getToken } = useAuth();
  const [query, setQuery] = useState('');
  const [debouncedQuery, setDebouncedQuery] = useState('');
  const [plan, setPlan] = useState('');
  const [status, setStatus] = useState('');
  const [users, setUsers] = useState<UserRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => setDebouncedQuery(query.trim()), 300);
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [query]);

  const requestParams = useMemo(() => {
    const params = new URLSearchParams();
    if (debouncedQuery) params.set('q', debouncedQuery);
    if (plan) params.set('plan', plan);
    if (status) params.set('status', status);
    params.set('limit', '50');
    return params.toString();
  }, [debouncedQuery, plan, status]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    (async () => {
      try {
        const token = await getToken();
        const res = await fetch(`/api/super-admin/users?${requestParams}`, {
          credentials: 'include',
          headers: token ? { Authorization: `Bearer ${token}` } : {},
        });
        if (!res.ok) throw new Error(`Search failed (${res.status})`);
        const data = await res.json();
        if (!cancelled) setUsers(data.users || []);
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Search failed');
          setUsers([]);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [requestParams, getToken]);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">Users</h1>
        <p className="mt-1 text-sm text-gray-600 dark:text-gray-400">
          Search by email or name. All actions are audit-logged.
        </p>
      </div>

      <div className="flex flex-wrap gap-3">
        <input
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search email or name…"
          className="flex-1 min-w-[260px] rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 px-3 py-2 text-sm"
        />
        <select
          value={plan}
          onChange={(e) => setPlan(e.target.value)}
          className="rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 px-3 py-2 text-sm"
        >
          {PLAN_OPTIONS.map((p) => (
            <option key={p || 'all'} value={p}>
              {p ? `Plan: ${p}` : 'All plans'}
            </option>
          ))}
        </select>
        <select
          value={status}
          onChange={(e) => setStatus(e.target.value)}
          className="rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 px-3 py-2 text-sm"
        >
          {STATUS_OPTIONS.map((s) => (
            <option key={s || 'all'} value={s}>
              {s ? `Status: ${s}` : 'All statuses'}
            </option>
          ))}
        </select>
      </div>

      {error && (
        <div className="rounded-md border border-red-300 bg-red-50 dark:bg-red-900/20 px-3 py-2 text-sm text-red-700 dark:text-red-300">
          {error}
        </div>
      )}

      <div className="overflow-x-auto rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800">
        <table className="min-w-full text-sm">
          <thead className="bg-gray-50 dark:bg-gray-900/50">
            <tr>
              <Th>Email</Th>
              <Th>Name</Th>
              <Th>Plan</Th>
              <Th>Status</Th>
              <Th>Orgs</Th>
              <Th>Signed up</Th>
              <Th />
            </tr>
          </thead>
          <tbody>
            {loading && (
              <tr>
                <td colSpan={7} className="px-4 py-6 text-center text-gray-500">
                  Loading…
                </td>
              </tr>
            )}
            {!loading && users.length === 0 && (
              <tr>
                <td colSpan={7} className="px-4 py-6 text-center text-gray-500">
                  No users match these filters.
                </td>
              </tr>
            )}
            {users.map((u) => (
              <tr
                key={u.clerk_id}
                className="border-t border-gray-100 dark:border-gray-700/50"
              >
                <Td>{u.email}</Td>
                <Td>{u.name || '—'}</Td>
                <Td>{u.subscription_status || 'free'}</Td>
                <Td>
                  <StatusBadge status={u.account_status || 'active'} />
                </Td>
                <Td>{u.org_count ?? 0}</Td>
                <Td>{u.signup_at ? new Date(u.signup_at).toLocaleDateString() : '—'}</Td>
                <Td>
                  <Link
                    href={`/super-admin/users/${u.clerk_id}`}
                    className="text-blue-600 hover:underline"
                  >
                    Open →
                  </Link>
                </Td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
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
    status === 'suspended' || status === 'banned'
      ? 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-200'
      : status === 'deleted'
      ? 'bg-gray-200 text-gray-600 dark:bg-gray-800 dark:text-gray-400'
      : 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-200';
  return (
    <span className={`inline-block rounded px-2 py-0.5 text-xs font-medium ${tone}`}>
      {status}
    </span>
  );
}
