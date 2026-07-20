/**
 * @vitest-environment jsdom
 *
 * Verifies `/dashboard` delegates to EmpireHomePage when the request
 * targets the chess-empire tenant, and falls back to the generic Chesster
 * dashboard everywhere else.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import React from 'react';
import { cleanup, render } from '@testing-library/react';

const headersStore: { current: Record<string, string> } = { current: {} };
vi.mock('next/headers', () => ({
  headers: async () => ({
    get: (name: string) => headersStore.current[name.toLowerCase()] ?? null,
  }),
}));

// redirect() throws NEXT_REDIRECT in Next; mirror that so the switch stops.
class RedirectError extends Error {
  constructor(public url: string) {
    super(`NEXT_REDIRECT:${url}`);
  }
}
const redirect = vi.fn((url: string) => {
  throw new RedirectError(url);
});
vi.mock('next/navigation', () => ({
  redirect: (url: string) => redirect(url),
}));

const authStore: { current: { userId: string | null } } = {
  current: { userId: null },
};
vi.mock('@clerk/nextjs/server', () => ({
  auth: async () => authStore.current,
}));

const memberStore: {
  studentId: string | null;
  state: 'no_link' | 'pending_confirm' | 'verified';
  throws: boolean;
} = { studentId: null, state: 'no_link', throws: false };
vi.mock('@/lib/chess-empire-member', () => ({
  getMembershipState: vi.fn(async () => {
    if (memberStore.throws) throw new Error('membership db down');
    return {
      state: memberStore.state,
      studentId: memberStore.studentId,
      memberId: memberStore.studentId ? 'mem-x' : null,
      role: 'student',
    };
  }),
}));

const ceStore: { profile: unknown } = { profile: null };
vi.mock('@/lib/chess-empire-client', () => ({
  getStudentProfile: vi.fn(async () => ceStore.profile),
  getStudentRatings: vi.fn(async () => []),
  getStudentAchievements: vi.fn(async () => []),
  getStudentRank: vi.fn(async () => ({
    branch_rank: null,
    school_rank: null,
    branch_size: null,
    school_size: null,
  })),
}));

vi.mock('@/components/empire/EmpireHomePage', () => ({
  __esModule: true,
  default: (props: {
    state: 'verified' | 'pending_confirm' | 'no_link';
    studentDisplayName: string | null;
    profile?: { id: string };
  }) => (
    <div
      data-testid="empire-home"
      data-state={props.state}
      data-name={props.studentDisplayName ?? ''}
    />
  ),
}));

// The no_link state wraps EmpireHomePage in a client poller; stub it to just
// render its children so this delegation test stays focused (its own behavior
// is covered in EmpireNoLinkClient.test).
vi.mock('@/components/empire/EmpireNoLinkClient', () => ({
  __esModule: true,
  default: (props: { children: React.ReactNode }) => <>{props.children}</>,
}));

vi.mock('../ChessterDashboard', () => ({
  __esModule: true,
  default: () => <div data-testid="chesster-dashboard" />,
}));

beforeEach(() => {
  headersStore.current = {};
  authStore.current = { userId: null };
  memberStore.studentId = null;
  memberStore.state = 'no_link';
  memberStore.throws = false;
  ceStore.profile = null;
  redirect.mockClear();
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe('/dashboard tenant delegation', () => {
  it('renders EmpireHomePage when host is chess-empire and user is verified', async () => {
    headersStore.current = {
      'x-org-id': 'org-ce',
      'x-org-slug': 'chess-empire',
    };
    authStore.current = { userId: 'user-1' };
    memberStore.state = 'verified';
    memberStore.studentId = 'stu-ali';
    ceStore.profile = {
      id: 'stu-ali',
      first_name: 'Ali',
      last_name: 'M.',
      branch_id: 'br-1',
      status: 'active',
      date_of_birth: null,
    };

    const Page = (await import('../page')).default;
    const ui = await Page();
    const { getByTestId, queryByTestId } = render(ui);
    const home = getByTestId('empire-home');
    expect(home.getAttribute('data-state')).toBe('verified');
    expect(home.getAttribute('data-name')).toBe('Ali');
    expect(queryByTestId('chesster-dashboard')).toBeNull();
  });

  it('renders EmpireHomePage in no_link state when host is chess-empire but no CE link', async () => {
    headersStore.current = {
      'x-org-id': 'org-ce',
      'x-org-slug': 'chess-empire',
    };
    authStore.current = { userId: 'user-1' };
    memberStore.state = 'no_link';
    memberStore.studentId = null;

    const Page = (await import('../page')).default;
    const ui = await Page();
    const { getByTestId, queryByTestId } = render(ui);
    expect(getByTestId('empire-home').getAttribute('data-state')).toBe('no_link');
    expect(queryByTestId('chesster-dashboard')).toBeNull();
  });

  it('falls back to Chesster dashboard when host is not chess-empire', async () => {
    headersStore.current = {
      'x-org-id': 'org-other',
      'x-org-slug': 'some-other-school',
    };

    const Page = (await import('../page')).default;
    const ui = await Page();
    const { getByTestId, queryByTestId } = render(ui);
    expect(getByTestId('chesster-dashboard')).toBeTruthy();
    expect(queryByTestId('empire-home')).toBeNull();
  });

  it('falls back to Chesster dashboard on apex (no org headers)', async () => {
    headersStore.current = {};

    const Page = (await import('../page')).default;
    const ui = await Page();
    const { getByTestId, queryByTestId } = render(ui);
    expect(getByTestId('chesster-dashboard')).toBeTruthy();
    expect(queryByTestId('empire-home')).toBeNull();
  });

  it('redirects to sign-in (never Chesster dashboard) when unsigned on chess-empire', async () => {
    headersStore.current = {
      'x-org-id': 'org-ce',
      'x-org-slug': 'chess-empire',
    };
    authStore.current = { userId: null };

    const Page = (await import('../page')).default;
    // auth_null → redirect() throws NEXT_REDIRECT; the generic dashboard is
    // never reached on the tenant host.
    await expect(Page()).rejects.toThrow('NEXT_REDIRECT');
    expect(redirect).toHaveBeenCalledWith('/sign-in?redirect_url=/dashboard');
  });

  it('renders the error/retry UI (never Chesster dashboard) on a lookup_error on chess-empire', async () => {
    headersStore.current = {
      'x-org-id': 'org-ce',
      'x-org-slug': 'chess-empire',
    };
    authStore.current = { userId: 'user-1' };
    memberStore.throws = true;

    const Page = (await import('../page')).default;
    const ui = await Page();
    const { getByText, queryByTestId } = render(ui);
    expect(getByText('Retry')).toBeTruthy();
    expect(queryByTestId('chesster-dashboard')).toBeNull();
    expect(queryByTestId('empire-home')).toBeNull();
  });
});
