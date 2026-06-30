/**
 * @vitest-environment jsdom
 *
 * Smoke test for the non-CE flow: renders members, supports search,
 * invite form toggle, and remove call.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import React from 'react';
import { cleanup, render, fireEvent } from '@testing-library/react';

vi.mock('@/contexts/OrganizationContext', () => ({
  useOrganization: () => ({
    org: { id: 'org-other', slug: 'some-other-school', name: 'Other' },
    isWhiteLabel: true,
  }),
}));

import ClerkMembersPanel from '../ClerkMembersPanel';

function jsonResponse(body: unknown, init: ResponseInit = {}) {
  return new Response(JSON.stringify(body), {
    status: init.status ?? 200,
    headers: { 'content-type': 'application/json', ...(init.headers || {}) },
  });
}

beforeEach(() => {
  vi.clearAllMocks();
  // jsdom-shim confirm
  globalThis.confirm = () => true;
});
afterEach(() => cleanup());

async function flush() {
  for (let i = 0; i < 5; i++) await Promise.resolve();
}

describe('ClerkMembersPanel', () => {
  it('renders the member list', async () => {
    const fetchSpy = vi.fn(async () =>
      jsonResponse({
        members: [
          { id: '1', user_id: 'u-1', role: 'admin', joined_at: '2026-06-01', email: 'a@x.com', name: 'A' },
          { id: '2', user_id: 'u-2', role: 'student', joined_at: '2026-06-02', email: 'b@x.com', name: 'B' },
        ],
      }),
    );
    global.fetch = fetchSpy as unknown as typeof fetch;
    const { findByText } = render(<ClerkMembersPanel />);
    expect(await findByText('A')).toBeTruthy();
    expect(await findByText('B')).toBeTruthy();
  });

  it('search narrows the visible members', async () => {
    global.fetch = vi.fn(async () =>
      jsonResponse({
        members: [
          { id: '1', user_id: 'u-1', role: 'admin', joined_at: '2026-06-01', email: 'aaa@x.com', name: 'Alice' },
          { id: '2', user_id: 'u-2', role: 'student', joined_at: '2026-06-02', email: 'bbb@x.com', name: 'Bob' },
        ],
      }),
    ) as unknown as typeof fetch;
    const { findByText, container, queryByText } = render(<ClerkMembersPanel />);
    await findByText('Alice');
    const input = container.querySelector('input[type="text"]') as HTMLInputElement;
    fireEvent.change(input, { target: { value: 'bob' } });
    await flush();
    expect(queryByText('Alice')).toBeNull();
    expect(queryByText('Bob')).toBeTruthy();
  });

  it('Invite button toggles the invite form', async () => {
    global.fetch = vi.fn(async () => jsonResponse({ members: [] })) as unknown as typeof fetch;
    const { container, findByText } = render(<ClerkMembersPanel />);
    const inviteBtn = await findByText('Invite Member');
    fireEvent.click(inviteBtn);
    const emailInput = container.querySelector('input[type="email"]');
    expect(emailInput).toBeTruthy();
  });

  it('Remove triggers the DELETE call', async () => {
    const calls: { url: string; init?: RequestInit }[] = [];
    global.fetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === 'string' ? input : (input as Request).url;
      calls.push({ url, init });
      if (init?.method === 'DELETE') return jsonResponse({});
      return jsonResponse({
        members: [
          { id: '1', user_id: 'u-1', role: 'student', joined_at: '2026-06-01', email: '', name: 'Alice' },
        ],
      });
    }) as unknown as typeof fetch;
    const { findByText } = render(<ClerkMembersPanel />);
    const removeBtn = await findByText('Remove');
    fireEvent.click(removeBtn);
    await flush();
    expect(calls.some((c) => c.init?.method === 'DELETE')).toBe(true);
  });
});
