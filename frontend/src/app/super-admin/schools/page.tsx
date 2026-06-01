'use client';

import { useAuth } from '@clerk/nextjs';
import Link from 'next/link';
import { useEffect, useMemo, useRef, useState } from 'react';

interface SchoolRow {
  id: string;
  slug: string;
  name: string;
  status: 'active' | 'suspended' | 'trial' | string | null;
  plan: string | null;
  member_count: number;
  student_count: number | null;
  custom_domain: string | null;
  custom_domain_status: string | null;
  created_at: string | null;
}

interface ListResponse {
  items: SchoolRow[];
  total: number;
}

const STATUS_FILTERS: Array<{ key: string; label: string }> = [
  { key: '', label: 'All' },
  { key: 'active', label: 'Active' },
  { key: 'suspended', label: 'Suspended' },
  { key: 'trial', label: 'Trial' },
];

const PAGE_SIZE = 50;

export default function SuperAdminSchoolsPage() {
  const { getToken } = useAuth();
  const [query, setQuery] = useState('');
  const [debouncedQuery, setDebouncedQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [offset, setOffset] = useState(0);
  const [items, setItems] = useState<SchoolRow[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      setDebouncedQuery(query.trim());
      setOffset(0);
    }, 300);
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [query]);

  const queryString = useMemo(() => {
    const params = new URLSearchParams();
    if (debouncedQuery) params.set('q', debouncedQuery);
    if (statusFilter) params.set('status', statusFilter);
    params.set('limit', String(PAGE_SIZE));
    params.set('offset', String(offset));
    return params.toString();
  }, [debouncedQuery, statusFilter, offset]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    (async () => {
      try {
        const token = await getToken();
        const res = await fetch(`/api/super-admin/organizations?${queryString}`, {
          credentials: 'include',
          headers: token ? { Authorization: `Bearer ${token}` } : {},
        });
        if (!res.ok) throw new Error(`Search failed (${res.status})`);
        const data: ListResponse = await res.json();
        if (!cancelled) {
          setItems(data.items || []);
          setTotal(data.total ?? 0);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Search failed');
          setItems([]);
          setTotal(0);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [queryString, getToken]);

  const pageStart = total === 0 ? 0 : offset + 1;
  const pageEnd = Math.min(offset + items.length, total);
  const hasPrev = offset > 0;
  const hasNext = offset + items.length < total;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">Schools</h1>
        <p className="mt-1 text-sm text-gray-600 dark:text-gray-400">
          Partner organizations on Chesster. All actions are audit-logged.
        </p>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <input
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search by slug or name…"
          className="flex-1 min-w-[260px] rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 px-3 py-2 text-sm"
        />
        <div className="flex flex-wrap gap-1">
          {STATUS_FILTERS.map((f) => (
            <button
              key={f.key || 'all'}
              type="button"
              onClick={() => {
                setStatusFilter(f.key);
                setOffset(0);
              }}
              className={`rounded-full px-3 py-1 text-xs font-medium border transition-colors ${
                statusFilter === f.key
                  ? 'bg-blue-600 text-white border-blue-600'
                  : 'bg-white dark:bg-gray-800 border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700'
              }`}
            >
              {f.label}
            </button>
          ))}
        </div>
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
              <Th>Name</Th>
              <Th>Status</Th>
              <Th>Plan</Th>
              <Th>Members</Th>
              <Th>Custom domain</Th>
              <Th>Created</Th>
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
            {!loading && items.length === 0 && (
              <tr>
                <td colSpan={7} className="px-4 py-6 text-center text-gray-500">
                  No organizations match these filters.
                </td>
              </tr>
            )}
            {items.map((row) => (
              <tr
                key={row.id}
                className="border-t border-gray-100 dark:border-gray-700/50"
              >
                <Td>
                  <div className="font-medium text-gray-900 dark:text-gray-100">{row.name}</div>
                  <div className="text-xs text-gray-500 dark:text-gray-400 font-mono">{row.slug}</div>
                </Td>
                <Td>
                  <StatusBadge status={row.status || 'active'} />
                </Td>
                <Td>{row.plan || '—'}</Td>
                <Td>{row.member_count}</Td>
                <Td>
                  <DomainCell
                    domain={row.custom_domain}
                    status={row.custom_domain_status}
                  />
                </Td>
                <Td>
                  <span title={row.created_at || ''}>
                    {row.created_at ? formatRelative(row.created_at) : '—'}
                  </span>
                </Td>
                <Td>
                  <Link
                    href={`/super-admin/schools/${row.id}`}
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

      <div className="flex items-center justify-between text-sm text-gray-600 dark:text-gray-400">
        <span>
          {total > 0
            ? `Showing ${pageStart}–${pageEnd} of ${total}`
            : 'No results'}
        </span>
        <div className="flex gap-2">
          <button
            type="button"
            disabled={!hasPrev || loading}
            onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
            className="rounded-md border border-gray-300 dark:border-gray-600 px-3 py-1.5 text-xs disabled:opacity-50"
          >
            ← Prev
          </button>
          <button
            type="button"
            disabled={!hasNext || loading}
            onClick={() => setOffset(offset + PAGE_SIZE)}
            className="rounded-md border border-gray-300 dark:border-gray-600 px-3 py-1.5 text-xs disabled:opacity-50"
          >
            Next →
          </button>
        </div>
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
    status === 'suspended'
      ? 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-200'
      : status === 'trial'
      ? 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-200'
      : 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-200';
  return (
    <span className={`inline-block rounded px-2 py-0.5 text-xs font-medium ${tone}`}>
      {status}
    </span>
  );
}

function DomainCell({
  domain,
  status,
}: {
  domain: string | null;
  status: string | null;
}) {
  if (!domain) return <span className="text-gray-400">—</span>;
  if (status === 'active') {
    return <span className="font-mono text-xs">{domain}</span>;
  }
  return (
    <span
      className="font-mono text-xs text-gray-500 italic"
      title={`Domain status: ${status || 'unknown'}`}
    >
      {domain}
    </span>
  );
}

function formatRelative(iso: string): string {
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return iso;
  const diff = Date.now() - then;
  const day = 24 * 60 * 60 * 1000;
  if (diff < day) return 'today';
  if (diff < 2 * day) return 'yesterday';
  if (diff < 30 * day) return `${Math.floor(diff / day)}d ago`;
  if (diff < 365 * day) return `${Math.floor(diff / (30 * day))}mo ago`;
  return `${Math.floor(diff / (365 * day))}y ago`;
}
