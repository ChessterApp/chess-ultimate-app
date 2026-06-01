/**
 * @vitest-environment jsdom
 */
import { describe, it, expect, vi, afterEach } from 'vitest';
import React from 'react';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import SuperAdminSchoolDetailPage from '../page';

// Stable Clerk mock — must not produce a new object/function per render.
const stableGetToken = vi.fn().mockResolvedValue('test-token');
const stableAuth = { getToken: stableGetToken };
vi.mock('@clerk/nextjs', () => ({
  useAuth: () => stableAuth,
}));

vi.mock('next/link', () => ({
  default: ({
    children,
    href,
    ...props
  }: {
    children: React.ReactNode;
    href: string;
    [k: string]: unknown;
  }) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

vi.mock('next/navigation', () => ({
  useParams: () => ({ id: 'org-1' }),
}));

interface Detail {
  organization: {
    id: string;
    slug: string;
    name: string;
    status: string;
    custom_domain: string | null;
    custom_domain_status: string | null;
    contact_email: string | null;
    created_at: string;
  };
  billing: { plan: string | null; student_count: number | null } | null;
  members: Array<{
    id: string;
    user_id: string;
    role: string;
    joined_at?: string | null;
    email?: string | null;
  }>;
  audit: Array<{
    id: string;
    action: string;
    payload: Record<string, unknown> | null;
    created_at: string;
    admin_clerk_id: string;
  }>;
}

function makeDetail(overrides: Partial<Detail['organization']> = {}): Detail {
  return {
    organization: {
      id: 'org-1',
      slug: 'kings-academy',
      name: "King's Academy",
      status: 'active',
      custom_domain: null,
      custom_domain_status: null,
      contact_email: 'hi@kings.com',
      created_at: '2026-04-01T00:00:00Z',
      ...overrides,
    },
    billing: { plan: 'growth', student_count: 42 },
    members: [
      { id: 'm-1', user_id: 'user_owner', role: 'owner', email: 'owner@kings.com' },
      { id: 'm-2', user_id: 'user_teacher', role: 'teacher', email: 'teach@kings.com' },
    ],
    audit: [],
  };
}

interface FetchCall {
  url: string;
  method: string;
  body: unknown;
}

function installFetchMock(
  responses: Array<{
    match: (call: FetchCall) => boolean;
    response: { ok: boolean; status: number; body: unknown };
  }>,
) {
  const calls: FetchCall[] = [];
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === 'string' ? input : input.toString();
    const method = (init?.method || 'GET').toUpperCase();
    const body = init?.body ? JSON.parse(init.body as string) : undefined;
    const call: FetchCall = { url, method, body };
    calls.push(call);
    const matched = responses.find((r) => r.match(call));
    if (!matched) throw new Error(`No mock response matched: ${method} ${url}`);
    return {
      ok: matched.response.ok,
      status: matched.response.status,
      json: async () => matched.response.body,
    } as Response;
  });
  // @ts-expect-error override global fetch
  global.fetch = fetchMock;
  return { calls, fetchMock };
}

describe('SuperAdminSchoolDetailPage', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('Suspend modal blocks submit when reason <3 chars; success re-fetches and updates status badge', async () => {
    let detail = makeDetail();
    const { calls } = installFetchMock([
      {
        match: (c) => c.url.endsWith('/api/super-admin/organizations/org-1') && c.method === 'GET',
        response: {
          ok: true,
          status: 200,
          // Return the latest detail when called.
          get body() {
            return detail;
          },
        },
      },
      {
        match: (c) =>
          c.url.endsWith('/api/super-admin/organizations/org-1/suspend') && c.method === 'POST',
        response: {
          ok: true,
          status: 200,
          body: { status: 'suspended', prior_status: 'active', idempotent: false },
        },
      },
    ]);

    render(<SuperAdminSchoolDetailPage />);

    await waitFor(() => expect(screen.getByText("King's Academy")).toBeTruthy());

    // Open suspend modal.
    fireEvent.click(screen.getByText('Suspend'));
    const confirmBtn = screen.getByText('Confirm suspend') as HTMLButtonElement;
    expect(confirmBtn.disabled).toBe(true);

    const textarea = screen.getByPlaceholderText('Reason (min 3 chars)') as HTMLTextAreaElement;
    fireEvent.change(textarea, { target: { value: 'ab' } });
    expect(confirmBtn.disabled).toBe(true);

    fireEvent.change(textarea, { target: { value: 'non-payment' } });
    expect(confirmBtn.disabled).toBe(false);

    // After confirming, server flips status. Update the closure so the next GET reflects it.
    detail = makeDetail({ status: 'suspended' });

    await act(async () => {
      fireEvent.click(confirmBtn);
    });

    await waitFor(() => {
      const suspendPost = calls.find((c) => c.method === 'POST' && c.url.endsWith('/suspend'));
      expect(suspendPost).toBeDefined();
      expect(suspendPost?.body).toEqual({ reason: 'non-payment' });
    });

    // The detail page re-fetches and the badge should now read "suspended".
    await waitFor(() => {
      const badges = screen.getAllByText('suspended');
      expect(badges.length).toBeGreaterThan(0);
    });
  });

  it('Promote modal: confirm only enabled when a non-owner member is selected with a reason', async () => {
    installFetchMock([
      {
        match: (c) => c.method === 'GET',
        response: { ok: true, status: 200, body: makeDetail() },
      },
    ]);

    render(<SuperAdminSchoolDetailPage />);
    await waitFor(() => expect(screen.getByText("King's Academy")).toBeTruthy());

    // Open the promote modal.
    fireEvent.click(screen.getByText('Promote owner'));
    const confirm = screen.getByText('Confirm promote') as HTMLButtonElement;
    expect(confirm.disabled).toBe(true);

    // Select the teacher (the only non-owner).
    const select = screen.getByRole('combobox') as HTMLSelectElement;
    fireEvent.change(select, { target: { value: 'user_teacher' } });
    expect(confirm.disabled).toBe(true); // still need reason

    const reason = screen.getByPlaceholderText('Reason (min 3 chars)') as HTMLTextAreaElement;
    fireEvent.change(reason, { target: { value: 'handoff' } });
    expect(confirm.disabled).toBe(false);
  });
});
