/**
 * @vitest-environment jsdom
 *
 * UI smoke tests for the Phase 4 ChessEmpirePanel: header counters,
 * three tabs, derivation of the unregistered set, branch/coach filters,
 * and per-row freeze action.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import React from 'react';
import { cleanup, render, fireEvent } from '@testing-library/react';

vi.mock('next-intl', () => ({
  useTranslations: () => (key: string, opts?: Record<string, unknown>) =>
    opts ? `${key}:${JSON.stringify(opts)}` : key,
}));

vi.mock('@/contexts/OrganizationContext', () => ({
  useOrganization: () => ({
    org: { id: 'org-ce', slug: 'chess-empire', name: 'CE' },
    isWhiteLabel: true,
  }),
}));

import ChessEmpirePanel from '../ChessEmpirePanel';

interface PendingResolvers {
  resolve: (r: Response) => void;
  url: string;
  init?: RequestInit;
}

function jsonResponse(body: unknown, init: ResponseInit = {}) {
  return new Response(JSON.stringify(body), {
    status: init.status ?? 200,
    headers: { 'content-type': 'application/json', ...(init.headers || {}) },
  });
}

function setupFetch(handler: (url: string, init?: RequestInit) => Promise<Response>) {
  const spy = vi.fn(
    (input: string | Request | URL, init?: RequestInit) =>
      handler(typeof input === 'string' ? input : (input as Request).url, init),
  );
  global.fetch = spy as unknown as typeof fetch;
  return spy;
}

const ROSTER_PAYLOAD = {
  ceMembers: [
    {
      id: 'm-1',
      user_id: 'u-1',
      role: 'student',
      joined_at: '2026-06-15T00:00:00Z',
      email: 'a@example.com',
      name: null,
      external_student_id: 's-1',
      link_status: 'verified',
      link_verified_at: '2026-06-20T00:00:00Z',
      link_revoked_at: null,
    },
    {
      id: 'm-2',
      user_id: 'u-2',
      role: 'student',
      joined_at: '2026-06-22T00:00:00Z',
      email: null,
      name: 'B',
      external_student_id: 's-2',
      link_status: 'pending',
      link_verified_at: null,
      link_revoked_at: null,
    },
    {
      id: 'm-3',
      user_id: 'u-3',
      role: 'student',
      joined_at: '2026-06-10T00:00:00Z',
      email: null,
      name: null,
      external_student_id: 's-3',
      link_status: 'frozen',
      link_verified_at: '2026-06-12T00:00:00Z',
      link_revoked_at: null,
    },
  ],
  ceActiveStudents: [
    {
      id: 's-1',
      first_name: 'Aiman',
      last_name: 'Karim',
      branch_id: 'br-1',
      coach_id: 'co-1',
      status: 'active',
      current_razryad: '3',
    },
    {
      id: 's-2',
      first_name: 'Bek',
      last_name: 'Nur',
      branch_id: 'br-1',
      coach_id: 'co-1',
      status: 'active',
      current_razryad: null,
    },
    {
      id: 's-3',
      first_name: 'Cara',
      last_name: 'Sky',
      branch_id: 'br-2',
      coach_id: null,
      status: 'active',
      current_razryad: null,
    },
    // s-4 is active but not in ceMembers → "Not yet registered"
    {
      id: 's-4',
      first_name: 'Dana',
      last_name: 'Lim',
      branch_id: 'br-2',
      coach_id: null,
      status: 'active',
      current_razryad: null,
    },
  ],
  branches: [
    { id: 'br-1', name: 'Debut' },
    { id: 'br-2', name: 'Astana' },
  ],
  coaches: [{ id: 'co-1', full_name: 'Yerkezhan', branch_id: 'br-1' }],
};

const ONLINE_PAYLOAD = {
  ceMembers: [
    {
      id: 'on-1',
      user_id: 'u-on1',
      role: 'student',
      joined_at: '2026-06-15T00:00:00Z',
      email: 'trial@example.com',
      name: 'Trial User',
      external_student_id: 'x-1',
      external_source: 'online',
      link_status: 'verified',
      link_verified_at: '2026-06-15T00:00:00Z',
      link_revoked_at: null,
      access_expires_at: '2099-01-01T00:00:00Z', // clearly future → Trial
    },
    {
      id: 'on-2',
      user_id: 'u-on2',
      role: 'student',
      joined_at: '2026-05-01T00:00:00Z',
      email: 'expired@example.com',
      name: 'Expired User',
      external_student_id: 'x-2',
      external_source: 'online',
      link_status: 'verified',
      link_verified_at: '2026-05-01T00:00:00Z',
      link_revoked_at: null,
      access_expires_at: '2020-01-01T00:00:00Z', // clearly past → Expired
    },
    {
      id: 'on-3',
      user_id: 'u-on3',
      role: 'student',
      joined_at: '2026-04-01T00:00:00Z',
      email: 'full@example.com',
      name: 'Full User',
      external_student_id: 'x-3',
      external_source: 'online',
      link_status: 'verified',
      link_verified_at: '2026-04-01T00:00:00Z',
      link_revoked_at: null,
      access_expires_at: null, // null → Full
    },
  ],
  ceActiveStudents: [],
  branches: [],
  coaches: [],
};

async function flush() {
  for (let i = 0; i < 5; i++) {
    await Promise.resolve();
  }
}

beforeEach(() => {
  vi.clearAllMocks();
});

afterEach(() => {
  cleanup();
});

describe('ChessEmpirePanel', () => {
  it('renders header counters from the roster payload', async () => {
    setupFetch(async (url) => {
      if (url.includes('/chess-empire/roster')) return jsonResponse(ROSTER_PAYLOAD);
      return jsonResponse({});
    });
    const { findByTestId, container } = render(<ChessEmpirePanel />);
    const counters = await findByTestId('counters');
    expect(counters.textContent).toContain('counterRegisteredValue');
    // The verified count is 1, pending is 1, frozen is 1, revoked is 0.
    expect(container.textContent).toContain('counterPending');
  });

  it('renders three tabs with derived counts', async () => {
    setupFetch(async (url) => {
      if (url.includes('/chess-empire/roster')) return jsonResponse(ROSTER_PAYLOAD);
      return jsonResponse({});
    });
    const { findByTestId } = render(<ChessEmpirePanel />);
    const tabsEl = await findByTestId('tabs');
    // Registered = verified + frozen = 2; pending = 1; unregistered = 1 (s-4)
    expect(tabsEl.textContent).toContain('(2)');
    expect(tabsEl.textContent).toContain('(1)');
  });

  it('Not-yet-registered tab excludes students who are in ceMembers', async () => {
    setupFetch(async (url) => {
      if (url.includes('/chess-empire/roster')) return jsonResponse(ROSTER_PAYLOAD);
      return jsonResponse({});
    });
    const { findByTestId, queryByText, container } = render(<ChessEmpirePanel />);
    await findByTestId('tabs');
    fireEvent.click(await findByTestId('tab-unregistered'));
    await flush();
    // Only Dana Lim should remain.
    expect(container.textContent).toContain('Dana Lim');
    expect(queryByText(/Aiman Karim/)).toBeNull();
    expect(queryByText(/Bek Nur/)).toBeNull();
    expect(queryByText(/Cara Sky/)).toBeNull();
  });

  it('per-row Freeze action calls the freeze endpoint', async () => {
    const calls: { url: string; init?: RequestInit }[] = [];
    setupFetch(async (url, init) => {
      calls.push({ url, init });
      if (url.includes('/chess-empire/roster')) return jsonResponse(ROSTER_PAYLOAD);
      if (url.includes('/chess-empire/members/m-1/freeze')) {
        return jsonResponse({
          frozen: true,
          member: {
            ...ROSTER_PAYLOAD.ceMembers[0],
            link_status: 'frozen',
          },
        });
      }
      return jsonResponse({});
    });
    const { findByTestId, container } = render(<ChessEmpirePanel />);
    await findByTestId('tabs');
    // Default tab = registered. m-1 row should be present.
    const row = await findByTestId('row-m:m-1');
    const freezeBtn = Array.from(row.querySelectorAll('button')).find((b) =>
      b.textContent?.includes('freeze'),
    );
    expect(freezeBtn).toBeTruthy();
    fireEvent.click(freezeBtn!);
    await flush();
    expect(calls.some((c) => c.url.includes('/members/m-1/freeze'))).toBe(true);
    // After the call, the row should reflect the new status (unfreeze visible).
    await flush();
    expect(container.textContent).toContain('unfreeze');
  });

  it('Online tab renders Trial / Expired / Full badges', async () => {
    setupFetch(async (url) => {
      if (url.includes('/chess-empire/roster')) return jsonResponse(ONLINE_PAYLOAD);
      return jsonResponse({});
    });
    const { findByTestId, container } = render(<ChessEmpirePanel />);
    await findByTestId('tabs');
    fireEvent.click(await findByTestId('tab-online'));
    await flush();
    expect(container.textContent).toContain('Trial User');
    expect(container.textContent).toContain('Expired User');
    expect(container.textContent).toContain('Full User');
    // Badge labels come through as raw i18n keys under the test mock.
    expect(container.textContent).toContain('statusTrial');
    expect(container.textContent).toContain('statusExpired');
    expect(container.textContent).toContain('statusFull');
  });

  it('Upgrade to full fires PATCH with accessExpiresAt=null', async () => {
    vi.stubGlobal('confirm', () => true);
    const calls: { url: string; init?: RequestInit }[] = [];
    setupFetch(async (url, init) => {
      calls.push({ url, init });
      if (url.includes('/chess-empire/roster')) return jsonResponse(ONLINE_PAYLOAD);
      if (url.includes('/members/on-1/access')) {
        return jsonResponse({
          member: { ...ONLINE_PAYLOAD.ceMembers[0], access_expires_at: null },
        });
      }
      return jsonResponse({});
    });
    const { findByTestId } = render(<ChessEmpirePanel />);
    await findByTestId('tabs');
    fireEvent.click(await findByTestId('tab-online'));
    await flush();
    fireEvent.click(await findByTestId('online-upgrade-on-1'));
    await flush();
    const patch = calls.find((c) => c.url.includes('/members/on-1/access'));
    expect(patch).toBeTruthy();
    expect(patch!.init?.method).toBe('PATCH');
    expect(JSON.parse(patch!.init!.body as string)).toEqual({
      accessExpiresAt: null,
    });
    vi.unstubAllGlobals();
  });

  it('Change expiry converts Almaty wall-clock to UTC ISO', async () => {
    const calls: { url: string; init?: RequestInit }[] = [];
    setupFetch(async (url, init) => {
      calls.push({ url, init });
      if (url.includes('/chess-empire/roster')) return jsonResponse(ONLINE_PAYLOAD);
      if (url.includes('/members/on-3/access')) {
        return jsonResponse({
          member: {
            ...ONLINE_PAYLOAD.ceMembers[2],
            access_expires_at: '2026-06-15T07:00:00.000Z',
          },
        });
      }
      return jsonResponse({});
    });
    const { findByTestId } = render(<ChessEmpirePanel />);
    await findByTestId('tabs');
    fireEvent.click(await findByTestId('tab-online'));
    await flush();
    fireEvent.click(await findByTestId('online-change-expiry-on-3'));
    await flush();
    const input = (await findByTestId(
      'online-expiry-input-on-3',
    )) as HTMLInputElement;
    // 12:00 Almaty (UTC+5) → 07:00 UTC.
    fireEvent.change(input, { target: { value: '2026-06-15T12:00' } });
    fireEvent.click(await findByTestId('online-save-on-3'));
    await flush();
    const patch = calls.find((c) => c.url.includes('/members/on-3/access'));
    expect(patch).toBeTruthy();
    expect(patch!.init?.method).toBe('PATCH');
    expect(JSON.parse(patch!.init!.body as string)).toEqual({
      accessExpiresAt: '2026-06-15T07:00:00.000Z',
    });
  });

  it('branch filter narrows visible rows', async () => {
    setupFetch(async (url) => {
      if (url.includes('/chess-empire/roster')) return jsonResponse(ROSTER_PAYLOAD);
      return jsonResponse({});
    });
    const { findByTestId, container } = render(<ChessEmpirePanel />);
    await findByTestId('tabs');
    // Filter to br-2 (Astana). On Registered tab, only m-3 (s-3 → Cara Sky)
    // qualifies (since s-3 is in br-2).
    const branchSelect = container.querySelector(
      'select',
    ) as HTMLSelectElement | null;
    expect(branchSelect).toBeTruthy();
    fireEvent.change(branchSelect!, { target: { value: 'br-2' } });
    await flush();
    expect(container.textContent).toContain('Cara Sky');
    expect(container.textContent).not.toContain('Aiman Karim');
  });
});
