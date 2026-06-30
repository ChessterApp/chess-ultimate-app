'use client';

import { useEffect, useMemo, useState } from 'react';
import { useTranslations } from 'next-intl';
import { useOrganization } from '@/contexts/OrganizationContext';

type LinkStatus = 'pending' | 'verified' | 'frozen' | 'revoked' | string;

interface CeMemberRow {
  id: string;
  user_id: string;
  role: string;
  joined_at: string;
  email?: string | null;
  name?: string | null;
  external_student_id: string | null;
  link_status: LinkStatus;
  link_verified_at: string | null;
  link_revoked_at: string | null;
}

interface CEActiveStudent {
  id: string;
  first_name: string;
  last_name: string;
  date_of_birth?: string | null;
  status: string;
  branch_id: string;
  coach_id?: string | null;
  current_razryad?: string | null;
  current_league?: string | null;
}

interface CEBranch {
  id: string;
  name: string;
  address?: string | null;
}

interface CECoach {
  id: string;
  full_name: string;
  branch_id?: string | null;
}

interface BranchTokenRow {
  id: string;
  organization_id: string;
  external_branch_id: string;
  branch_name: string;
  token: string;
  expires_at: string | null;
  revoked_at: string | null;
  created_at: string;
  created_by: string | null;
}

interface RosterPayload {
  ceMembers: CeMemberRow[];
  ceActiveStudents: CEActiveStudent[];
  branches: CEBranch[];
  coaches: CECoach[];
}

type TabKey = 'registered' | 'pending' | 'unregistered';

interface StudentRow {
  key: string;
  memberId: string | null;
  externalStudentId: string | null;
  firstName: string;
  lastName: string;
  branchId: string;
  coachId: string | null;
  razryad: string | null;
  email: string | null;
  linkStatus: LinkStatus | null;
  linkVerifiedAt: string | null;
  joinedAt: string | null;
}

function shortId(id: string | null): string {
  if (!id) return '—';
  return id.length > 10 ? `${id.slice(0, 6)}…${id.slice(-3)}` : id;
}

function StatusBadge({ status, label }: { status: LinkStatus; label: string }) {
  const cls: Record<string, string> = {
    verified: 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-300',
    pending: 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300',
    frozen: 'bg-slate-200 text-slate-700 dark:bg-slate-700/40 dark:text-slate-300',
    revoked: 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300',
  };
  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${
        cls[status] || cls.frozen
      }`}
    >
      {label}
    </span>
  );
}

export default function ChessEmpirePanel() {
  const t = useTranslations('adminCe');
  const { org } = useOrganization();
  const [data, setData] = useState<RosterPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [tab, setTab] = useState<TabKey>('registered');
  const [search, setSearch] = useState('');
  const [branchFilter, setBranchFilter] = useState('all');
  const [coachFilter, setCoachFilter] = useState('all');
  const [statusFilter, setStatusFilter] = useState<'all' | LinkStatus>('all');

  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [busyMemberIds, setBusyMemberIds] = useState<Set<string>>(new Set());
  const [toast, setToast] = useState<string | null>(null);

  const [showBranchManager, setShowBranchManager] = useState(false);
  const [tokens, setTokens] = useState<BranchTokenRow[]>([]);
  const [tokensLoading, setTokensLoading] = useState(false);
  const [tokenBusy, setTokenBusy] = useState<Set<string>>(new Set());

  useEffect(() => {
    if (!org?.id) return;
    void fetchRoster();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [org?.id]);

  async function fetchRoster() {
    if (!org?.id) return;
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(
        `/api/admin/organizations/${org.id}/chess-empire/roster`,
      );
      if (!res.ok) {
        setError(t('errorLoad'));
        setData({ ceMembers: [], ceActiveStudents: [], branches: [], coaches: [] });
        return;
      }
      const payload = (await res.json()) as RosterPayload;
      setData(payload);
    } catch {
      setError(t('errorLoad'));
      setData({ ceMembers: [], ceActiveStudents: [], branches: [], coaches: [] });
    } finally {
      setLoading(false);
    }
  }

  async function fetchTokens() {
    if (!org?.id) return;
    setTokensLoading(true);
    try {
      const res = await fetch(
        `/api/admin/organizations/${org.id}/chess-empire/branch-tokens`,
      );
      if (res.ok) {
        const payload = (await res.json()) as { tokens: BranchTokenRow[] };
        setTokens(payload.tokens || []);
      }
    } finally {
      setTokensLoading(false);
    }
  }

  function toggleBranchManager() {
    const next = !showBranchManager;
    setShowBranchManager(next);
    if (next && tokens.length === 0) void fetchTokens();
  }

  const branches = useMemo<CEBranch[]>(
    () => data?.branches ?? [],
    [data],
  );
  const coaches = useMemo<CECoach[]>(() => data?.coaches ?? [], [data]);
  const ceMembers = useMemo<CeMemberRow[]>(
    () => data?.ceMembers ?? [],
    [data],
  );
  const ceActiveStudents = useMemo<CEActiveStudent[]>(
    () => data?.ceActiveStudents ?? [],
    [data],
  );

  const studentByExternalId = useMemo(() => {
    const m = new Map<string, CEActiveStudent>();
    for (const s of ceActiveStudents) m.set(s.id, s);
    return m;
  }, [ceActiveStudents]);

  const branchById = useMemo(() => {
    const m = new Map<string, CEBranch>();
    for (const b of branches) m.set(b.id, b);
    return m;
  }, [branches]);

  const coachById = useMemo(() => {
    const m = new Map<string, CECoach>();
    for (const c of coaches) m.set(c.id, c);
    return m;
  }, [coaches]);

  const statusCounts = useMemo(() => {
    const counts = { verified: 0, pending: 0, frozen: 0, revoked: 0 };
    for (const m of ceMembers) {
      if (m.link_status === 'verified') counts.verified++;
      else if (m.link_status === 'pending') counts.pending++;
      else if (m.link_status === 'frozen') counts.frozen++;
      else if (m.link_status === 'revoked') counts.revoked++;
    }
    return counts;
  }, [ceMembers]);

  const totalActive = ceActiveStudents.length;

  function rowFromMember(m: CeMemberRow): StudentRow {
    const student = m.external_student_id
      ? studentByExternalId.get(m.external_student_id)
      : undefined;
    return {
      key: `m:${m.id}`,
      memberId: m.id,
      externalStudentId: m.external_student_id,
      firstName: student?.first_name ?? m.name ?? '',
      lastName: student?.last_name ?? '',
      branchId: student?.branch_id ?? '',
      coachId: student?.coach_id ?? null,
      razryad: student?.current_razryad ?? null,
      email: m.email ?? null,
      linkStatus: m.link_status,
      linkVerifiedAt: m.link_verified_at,
      joinedAt: m.joined_at,
    };
  }

  function rowFromActiveStudent(s: CEActiveStudent): StudentRow {
    return {
      key: `s:${s.id}`,
      memberId: null,
      externalStudentId: s.id,
      firstName: s.first_name,
      lastName: s.last_name,
      branchId: s.branch_id,
      coachId: s.coach_id ?? null,
      razryad: s.current_razryad ?? null,
      email: null,
      linkStatus: null,
      linkVerifiedAt: null,
      joinedAt: null,
    };
  }

  const linkedExternalIds = useMemo(() => {
    const s = new Set<string>();
    for (const m of ceMembers) {
      if (m.external_student_id) s.add(m.external_student_id);
    }
    return s;
  }, [ceMembers]);

  const rowsByTab: Record<TabKey, StudentRow[]> = useMemo(() => {
    const registered = ceMembers
      .filter((m) => m.link_status === 'verified' || m.link_status === 'frozen')
      .map(rowFromMember);
    const pending = ceMembers
      .filter((m) => m.link_status === 'pending')
      .map(rowFromMember);
    const unregistered = ceActiveStudents
      .filter((s) => !linkedExternalIds.has(s.id))
      .map(rowFromActiveStudent);
    return { registered, pending, unregistered };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ceMembers, ceActiveStudents, linkedExternalIds, studentByExternalId]);

  const visibleRows: StudentRow[] = useMemo(() => {
    let rows = rowsByTab[tab];
    if (branchFilter !== 'all') {
      rows = rows.filter((r) => r.branchId === branchFilter);
    }
    if (coachFilter !== 'all') {
      rows = rows.filter((r) => r.coachId === coachFilter);
    }
    if (tab !== 'unregistered' && statusFilter !== 'all') {
      rows = rows.filter((r) => r.linkStatus === statusFilter);
    }
    const q = search.trim().toLowerCase();
    if (q) {
      rows = rows.filter((r) => {
        const full = `${r.firstName} ${r.lastName}`.toLowerCase();
        return full.includes(q);
      });
    }
    return rows;
  }, [rowsByTab, tab, branchFilter, coachFilter, statusFilter, search]);

  function flashToast(msg: string) {
    setToast(msg);
    setTimeout(() => setToast((cur) => (cur === msg ? null : cur)), 3000);
  }

  function markBusy(memberId: string, busy: boolean) {
    setBusyMemberIds((prev) => {
      const next = new Set(prev);
      if (busy) next.add(memberId);
      else next.delete(memberId);
      return next;
    });
  }

  async function callMemberAction(
    memberId: string,
    action: 'freeze' | 'unfreeze' | 'revoke',
  ): Promise<CeMemberRow | null> {
    if (!org?.id) return null;
    markBusy(memberId, true);
    try {
      const path =
        action === 'revoke'
          ? `members/${memberId}/revoke`
          : `members/${memberId}/freeze`;
      const body =
        action === 'unfreeze' ? JSON.stringify({ unfreeze: true }) : undefined;
      const res = await fetch(
        `/api/admin/organizations/${org.id}/chess-empire/${path}`,
        {
          method: 'POST',
          headers: body ? { 'Content-Type': 'application/json' } : undefined,
          body,
        },
      );
      if (!res.ok) return null;
      const payload = (await res.json()) as { member?: CeMemberRow };
      const updated = payload.member ?? null;
      if (updated) {
        setData((cur) => {
          if (!cur) return cur;
          return {
            ...cur,
            ceMembers: cur.ceMembers.map((m) =>
              m.id === updated.id ? { ...m, ...updated } : m,
            ),
          };
        });
      }
      return updated;
    } finally {
      markBusy(memberId, false);
    }
  }

  async function handleRowFreeze(row: StudentRow) {
    if (!row.memberId) return;
    const isFrozen = row.linkStatus === 'frozen';
    await callMemberAction(row.memberId, isFrozen ? 'unfreeze' : 'freeze');
  }

  async function handleRowRevoke(row: StudentRow) {
    if (!row.memberId) return;
    if (!confirm(t('confirmRevokeRow'))) return;
    await callMemberAction(row.memberId, 'revoke');
  }

  function toggleSelected(key: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }

  function toggleSelectAll() {
    const selectableKeys = visibleRows
      .filter((r) => r.memberId)
      .map((r) => r.key);
    if (selectableKeys.every((k) => selected.has(k))) {
      setSelected((prev) => {
        const next = new Set(prev);
        selectableKeys.forEach((k) => next.delete(k));
        return next;
      });
    } else {
      setSelected((prev) => {
        const next = new Set(prev);
        selectableKeys.forEach((k) => next.add(k));
        return next;
      });
    }
  }

  async function bulkApply(action: 'freeze' | 'unfreeze' | 'revoke') {
    if (selected.size === 0) return;
    if (action === 'revoke' && !confirm(t('confirmBulkRevoke'))) return;
    const targets = visibleRows.filter(
      (r) => r.memberId && selected.has(r.key),
    );
    for (const row of targets) {
      if (!row.memberId) continue;
      await callMemberAction(row.memberId, action);
    }
    setSelected(new Set());
  }

  function markTokenBusy(id: string, busy: boolean) {
    setTokenBusy((prev) => {
      const next = new Set(prev);
      if (busy) next.add(id);
      else next.delete(id);
      return next;
    });
  }

  async function copyToClipboard(text: string) {
    try {
      if (navigator?.clipboard?.writeText) {
        await navigator.clipboard.writeText(text);
      }
    } catch {
      // best-effort
    }
  }

  function tokenUrl(token: string): string {
    return `https://chess-empire.chesster.io/welcome/${token}`;
  }

  async function handleRotate(row: BranchTokenRow) {
    if (!org?.id) return;
    if (!confirm(t('confirmRotateToken'))) return;
    markTokenBusy(row.id, true);
    try {
      const res = await fetch(
        `/api/admin/organizations/${org.id}/chess-empire/branch-tokens/${row.id}/rotate`,
        { method: 'POST' },
      );
      if (!res.ok) return;
      const payload = (await res.json()) as {
        revoked: BranchTokenRow;
        created: BranchTokenRow;
        url: string;
      };
      setTokens((cur) => [
        ...cur.map((c) => (c.id === payload.revoked.id ? payload.revoked : c)),
        payload.created,
      ]);
      await copyToClipboard(payload.url);
      flashToast(t('toastRotateCopied'));
    } finally {
      markTokenBusy(row.id, false);
    }
  }

  async function handleRevokeToken(row: BranchTokenRow) {
    if (!org?.id) return;
    if (!confirm(t('confirmRevokeToken'))) return;
    markTokenBusy(row.id, true);
    try {
      const res = await fetch(
        `/api/admin/organizations/${org.id}/chess-empire/branch-tokens/${row.id}/revoke`,
        { method: 'POST' },
      );
      if (!res.ok) return;
      const payload = (await res.json()) as { revoked: BranchTokenRow };
      setTokens((cur) =>
        cur.map((c) => (c.id === payload.revoked.id ? payload.revoked : c)),
      );
    } finally {
      markTokenBusy(row.id, false);
    }
  }

  async function handleGenerateForBranch(branch: CEBranch) {
    if (!org?.id) return;
    markTokenBusy(`new:${branch.id}`, true);
    try {
      const res = await fetch(
        `/api/admin/organizations/${org.id}/chess-empire/branch-tokens`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ branchId: branch.id, branchName: branch.name }),
        },
      );
      if (!res.ok) return;
      const payload = (await res.json()) as {
        created: BranchTokenRow;
        url: string;
      };
      setTokens((cur) => [...cur, payload.created]);
      await copyToClipboard(payload.url);
      flashToast(t('toastRotateCopied'));
    } finally {
      markTokenBusy(`new:${branch.id}`, false);
    }
  }

  const registeredCount = statusCounts.verified;
  const registeredPct = totalActive > 0
    ? Math.round((registeredCount / totalActive) * 100)
    : 0;

  const filteredCoaches = useMemo(() => {
    if (branchFilter === 'all') return coaches;
    return coaches.filter((c) => !c.branch_id || c.branch_id === branchFilter);
  }, [coaches, branchFilter]);

  const tokensByBranch = useMemo(() => {
    const m = new Map<string, BranchTokenRow[]>();
    for (const tok of tokens) {
      const arr = m.get(tok.external_branch_id) || [];
      arr.push(tok);
      m.set(tok.external_branch_id, arr);
    }
    return m;
  }, [tokens]);

  const branchesNeedingToken = useMemo(() => {
    return branches.filter((b) => {
      const list = tokensByBranch.get(b.id) || [];
      return !list.some((tok) => !tok.revoked_at);
    });
  }, [branches, tokensByBranch]);

  const selectableInView = visibleRows.filter((r) => r.memberId).length;
  const allInViewSelected =
    selectableInView > 0 &&
    visibleRows.every((r) => !r.memberId || selected.has(r.key));

  return (
    <div data-testid="chess-empire-panel">
      <div className="flex items-center justify-between mb-6 flex-wrap gap-3">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">
          {t('title')}
        </h1>
        <button
          onClick={toggleBranchManager}
          className="px-4 py-2 text-sm font-medium text-white rounded-lg"
          style={{ backgroundColor: 'var(--brand-primary)' }}
        >
          {t('manageBranchLinks')}
        </button>
      </div>

      {/* Header counters */}
      <div
        data-testid="counters"
        className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6"
      >
        <div className="rounded-xl border border-gray-200 dark:border-gray-700 p-4 bg-white dark:bg-gray-800">
          <div className="text-xs text-gray-500 dark:text-gray-400">
            {t('counterRegistered')}
          </div>
          <div className="text-lg font-semibold text-gray-900 dark:text-gray-100">
            {t('counterRegisteredValue', {
              registered: registeredCount,
              total: totalActive,
              percent: registeredPct,
            })}
          </div>
        </div>
        <div className="rounded-xl border border-gray-200 dark:border-gray-700 p-4 bg-white dark:bg-gray-800">
          <div className="text-xs text-gray-500 dark:text-gray-400">
            {t('counterPending')}
          </div>
          <div className="text-lg font-semibold text-gray-900 dark:text-gray-100">
            {statusCounts.pending}
          </div>
        </div>
        <div className="rounded-xl border border-gray-200 dark:border-gray-700 p-4 bg-white dark:bg-gray-800">
          <div className="text-xs text-gray-500 dark:text-gray-400">
            {t('counterFrozen')}
          </div>
          <div className="text-lg font-semibold text-gray-900 dark:text-gray-100">
            {statusCounts.frozen}
          </div>
        </div>
        <div className="rounded-xl border border-gray-200 dark:border-gray-700 p-4 bg-white dark:bg-gray-800">
          <div className="text-xs text-gray-500 dark:text-gray-400">
            {t('counterRevoked')}
          </div>
          <div className="text-lg font-semibold text-gray-900 dark:text-gray-100">
            {statusCounts.revoked}
          </div>
        </div>
      </div>

      {/* Branch invite manager */}
      {showBranchManager && (
        <div
          data-testid="branch-manager"
          className="mb-6 rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 p-4"
        >
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
              {t('branchManagerTitle')}
            </h2>
            <button
              onClick={toggleBranchManager}
              className="text-xs text-gray-500 hover:text-gray-700 dark:text-gray-400"
            >
              {t('close')}
            </button>
          </div>
          {tokensLoading ? (
            <div className="text-sm text-gray-500">{t('loading')}</div>
          ) : (
            <div className="grid gap-3">
              {tokens.length === 0 && (
                <div className="text-sm text-gray-500">{t('noTokens')}</div>
              )}
              {tokens.map((tok) => {
                const active = !tok.revoked_at;
                const url = tokenUrl(tok.token);
                return (
                  <div
                    key={tok.id}
                    data-testid={`token-${tok.id}`}
                    className={`p-3 rounded-lg border ${
                      active
                        ? 'border-gray-200 dark:border-gray-700'
                        : 'border-gray-200 dark:border-gray-700 opacity-60'
                    }`}
                  >
                    <div className="flex items-center justify-between gap-2 flex-wrap">
                      <div className="flex items-center gap-2">
                        <span className="font-medium text-gray-900 dark:text-gray-100">
                          {tok.branch_name}
                        </span>
                        <StatusBadge
                          status={active ? 'verified' : 'revoked'}
                          label={active ? t('tokenActive') : t('tokenRevoked')}
                        />
                      </div>
                      <div className="flex gap-2">
                        <button
                          onClick={() => copyToClipboard(url)}
                          className="text-xs px-2 py-1 rounded border border-gray-300 dark:border-gray-600"
                        >
                          {t('copyLink')}
                        </button>
                        <button
                          onClick={() => handleRotate(tok)}
                          disabled={tokenBusy.has(tok.id)}
                          className="text-xs px-2 py-1 rounded border border-gray-300 dark:border-gray-600 disabled:opacity-50"
                        >
                          {t('rotate')}
                        </button>
                        {active && (
                          <button
                            onClick={() => handleRevokeToken(tok)}
                            disabled={tokenBusy.has(tok.id)}
                            className="text-xs px-2 py-1 rounded border border-red-300 text-red-700 dark:text-red-300 disabled:opacity-50"
                          >
                            {t('revokeToken')}
                          </button>
                        )}
                      </div>
                    </div>
                    <div className="mt-1 text-xs text-gray-500 break-all font-mono">
                      {url}
                    </div>
                    <div className="mt-1 text-xs text-gray-400">
                      {t('createdAt')}:{' '}
                      {tok.created_at
                        ? new Date(tok.created_at).toLocaleString()
                        : '—'}
                      {tok.revoked_at && (
                        <>
                          {' · '}
                          {t('revokedAt')}:{' '}
                          {new Date(tok.revoked_at).toLocaleString()}
                        </>
                      )}
                    </div>
                  </div>
                );
              })}

              {branchesNeedingToken.map((branch) => (
                <div
                  key={`generate-${branch.id}`}
                  className="p-3 rounded-lg border border-dashed border-gray-300 dark:border-gray-600 flex items-center justify-between gap-2"
                >
                  <div className="text-sm text-gray-700 dark:text-gray-300">
                    {branch.name} — {t('noActiveToken')}
                  </div>
                  <button
                    onClick={() => handleGenerateForBranch(branch)}
                    disabled={tokenBusy.has(`new:${branch.id}`)}
                    className="text-xs px-2 py-1 rounded text-white disabled:opacity-50"
                    style={{ backgroundColor: 'var(--brand-primary)' }}
                  >
                    {t('generateLink')}
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Tabs */}
      <div
        data-testid="tabs"
        className="flex gap-2 mb-4 border-b border-gray-200 dark:border-gray-700"
      >
        {(['registered', 'pending', 'unregistered'] as TabKey[]).map((k) => {
          const isActive = tab === k;
          const count = rowsByTab[k].length;
          return (
            <button
              key={k}
              onClick={() => {
                setTab(k);
                setSelected(new Set());
              }}
              data-testid={`tab-${k}`}
              className={`px-3 py-2 text-sm font-medium border-b-2 ${
                isActive
                  ? 'border-current text-gray-900 dark:text-gray-100'
                  : 'border-transparent text-gray-500'
              }`}
            >
              {t(`tab.${k}`)} ({count})
            </button>
          );
        })}
      </div>

      {/* Filters */}
      <div className="flex flex-wrap gap-2 mb-4">
        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder={t('searchPlaceholder')}
          className="flex-1 min-w-[180px] max-w-sm px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-sm"
        />
        <select
          value={branchFilter}
          onChange={(e) => setBranchFilter(e.target.value)}
          className="px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-sm"
        >
          <option value="all">{t('filterAllBranches')}</option>
          {branches.map((b) => (
            <option key={b.id} value={b.id}>
              {b.name}
            </option>
          ))}
        </select>
        <select
          value={coachFilter}
          onChange={(e) => setCoachFilter(e.target.value)}
          className="px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-sm"
        >
          <option value="all">{t('filterAllCoaches')}</option>
          {filteredCoaches.map((c) => (
            <option key={c.id} value={c.id}>
              {c.full_name}
            </option>
          ))}
        </select>
        {tab !== 'unregistered' && (
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value as LinkStatus)}
            className="px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-sm"
          >
            <option value="all">{t('filterAllStatuses')}</option>
            <option value="verified">{t('statusVerified')}</option>
            <option value="pending">{t('statusPending')}</option>
            <option value="frozen">{t('statusFrozen')}</option>
            <option value="revoked">{t('statusRevoked')}</option>
          </select>
        )}
      </div>

      {/* Bulk actions */}
      {selected.size > 0 && (
        <div
          data-testid="bulk-actions"
          className="mb-3 flex items-center gap-2 px-3 py-2 rounded-lg bg-blue-50 dark:bg-blue-900/20 text-sm"
        >
          <span className="text-gray-700 dark:text-gray-200">
            {t('bulkSelected', { count: selected.size })}
          </span>
          <button
            onClick={() => bulkApply('freeze')}
            className="px-2 py-1 text-xs rounded border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800"
          >
            {t('bulkFreeze')}
          </button>
          <button
            onClick={() => bulkApply('unfreeze')}
            className="px-2 py-1 text-xs rounded border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800"
          >
            {t('bulkUnfreeze')}
          </button>
          <button
            onClick={() => bulkApply('revoke')}
            className="px-2 py-1 text-xs rounded border border-red-300 text-red-700 dark:text-red-300 bg-white dark:bg-gray-800"
          >
            {t('bulkRevoke')}
          </button>
          <button
            disabled
            title={t('comingSoon')}
            className="px-2 py-1 text-xs rounded border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 opacity-50 cursor-not-allowed"
          >
            {t('bulkResend')}
          </button>
        </div>
      )}

      {error && (
        <div className="mb-3 text-sm text-red-600 dark:text-red-400">{error}</div>
      )}

      {/* Table */}
      <div className="overflow-x-auto rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-200 dark:border-gray-700">
              <th className="px-3 py-3 w-8">
                {tab !== 'unregistered' && (
                  <input
                    type="checkbox"
                    aria-label={t('selectAll')}
                    checked={allInViewSelected}
                    onChange={toggleSelectAll}
                  />
                )}
              </th>
              <th className="text-left px-3 py-3 font-medium text-gray-500 dark:text-gray-400">
                {t('colName')}
              </th>
              <th className="text-left px-3 py-3 font-medium text-gray-500 dark:text-gray-400">
                {t('colStudentId')}
              </th>
              <th className="text-left px-3 py-3 font-medium text-gray-500 dark:text-gray-400">
                {t('colBranch')}
              </th>
              <th className="text-left px-3 py-3 font-medium text-gray-500 dark:text-gray-400">
                {t('colCoach')}
              </th>
              <th className="text-left px-3 py-3 font-medium text-gray-500 dark:text-gray-400">
                {t('colRazryad')}
              </th>
              <th className="text-left px-3 py-3 font-medium text-gray-500 dark:text-gray-400">
                {t('colEmail')}
              </th>
              <th className="text-left px-3 py-3 font-medium text-gray-500 dark:text-gray-400">
                {tab === 'pending' ? t('colJoinedAt') : t('colVerifiedAt')}
              </th>
              <th className="text-right px-3 py-3 font-medium text-gray-500 dark:text-gray-400">
                {t('colActions')}
              </th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={9} className="px-4 py-8 text-center text-gray-500">
                  {t('loading')}
                </td>
              </tr>
            ) : visibleRows.length === 0 ? (
              <tr>
                <td colSpan={9} className="px-4 py-8 text-center text-gray-500">
                  {t('empty')}
                </td>
              </tr>
            ) : (
              visibleRows.map((row) => {
                const busy = row.memberId
                  ? busyMemberIds.has(row.memberId)
                  : false;
                const branchName = row.branchId
                  ? branchById.get(row.branchId)?.name ?? '—'
                  : '—';
                const coachName = row.coachId
                  ? coachById.get(row.coachId)?.full_name ?? '—'
                  : '—';
                const dateField =
                  tab === 'pending' ? row.joinedAt : row.linkVerifiedAt;
                return (
                  <tr
                    key={row.key}
                    data-testid={`row-${row.key}`}
                    className="border-b border-gray-100 dark:border-gray-700 last:border-0"
                  >
                    <td className="px-3 py-2">
                      {row.memberId && (
                        <input
                          type="checkbox"
                          aria-label={t('selectRow')}
                          checked={selected.has(row.key)}
                          onChange={() => toggleSelected(row.key)}
                        />
                      )}
                    </td>
                    <td className="px-3 py-2">
                      <div className="font-medium text-gray-900 dark:text-gray-100">
                        {row.firstName} {row.lastName}
                      </div>
                      {row.linkStatus && (
                        <StatusBadge
                          status={row.linkStatus}
                          label={t(`status${
                            row.linkStatus.charAt(0).toUpperCase() +
                            row.linkStatus.slice(1)
                          }` as
                            | 'statusVerified'
                            | 'statusPending'
                            | 'statusFrozen'
                            | 'statusRevoked')}
                        />
                      )}
                    </td>
                    <td className="px-3 py-2">
                      <button
                        type="button"
                        onClick={() =>
                          row.externalStudentId &&
                          copyToClipboard(row.externalStudentId)
                        }
                        title={row.externalStudentId ?? ''}
                        className="font-mono text-xs text-gray-600 dark:text-gray-300 hover:underline"
                      >
                        {shortId(row.externalStudentId)}
                      </button>
                    </td>
                    <td className="px-3 py-2 text-gray-700 dark:text-gray-300">
                      {branchName}
                    </td>
                    <td className="px-3 py-2 text-gray-700 dark:text-gray-300">
                      {coachName}
                    </td>
                    <td className="px-3 py-2 text-gray-700 dark:text-gray-300">
                      {row.razryad ?? '—'}
                    </td>
                    <td className="px-3 py-2 text-gray-500">
                      {row.email ?? '—'}
                    </td>
                    <td className="px-3 py-2 text-gray-500">
                      {dateField
                        ? new Date(dateField).toLocaleDateString()
                        : '—'}
                    </td>
                    <td className="px-3 py-2 text-right">
                      {tab === 'unregistered' ? (
                        <button
                          disabled
                          title={t('comingSoon')}
                          className="text-xs text-gray-400 cursor-not-allowed"
                        >
                          {t('resendReminder')}
                        </button>
                      ) : tab === 'pending' ? (
                        <button
                          onClick={() => handleRowRevoke(row)}
                          disabled={busy}
                          className="text-xs text-red-600 hover:text-red-800 dark:text-red-400 disabled:opacity-50"
                        >
                          {busy ? t('working') : t('revoke')}
                        </button>
                      ) : (
                        <div className="flex justify-end gap-2 items-center">
                          {row.externalStudentId && (
                            <a
                              href={`https://chess-empire.chessempire.kz/students/${row.externalStudentId}`}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="text-xs text-blue-600 hover:underline dark:text-blue-400"
                            >
                              {t('viewProfile')}
                            </a>
                          )}
                          <button
                            onClick={() => handleRowFreeze(row)}
                            disabled={busy}
                            className="text-xs text-gray-700 dark:text-gray-200 disabled:opacity-50"
                          >
                            {busy
                              ? t('working')
                              : row.linkStatus === 'frozen'
                                ? t('unfreeze')
                                : t('freeze')}
                          </button>
                          <button
                            onClick={() => handleRowRevoke(row)}
                            disabled={busy}
                            className="text-xs text-red-600 hover:text-red-800 dark:text-red-400 disabled:opacity-50"
                          >
                            {busy ? t('working') : t('revoke')}
                          </button>
                        </div>
                      )}
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>

      {toast && (
        <div
          data-testid="toast"
          className="fixed bottom-4 right-4 px-3 py-2 rounded-lg bg-gray-900 text-white text-sm shadow-lg"
        >
          {toast}
        </div>
      )}
    </div>
  );
}
