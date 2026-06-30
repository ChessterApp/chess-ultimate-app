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
