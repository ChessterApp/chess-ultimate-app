/**
 * @vitest-environment jsdom
 *
 * Online-kind invite tokens now render the SAME roster-search flow
 * (`WelcomeFlow`) as branch tokens — the synthetic auto-register path
 * (`OnlineWelcomeFlow` + `/api/chess-empire/online/register`) was retired.
 *
 * These drive the server page end-to-end for a `kind='online'` token: it
 * resolves the token and renders the search flow, and the search request is
 * scoped to the Online branch token (`students/search?branchToken=<online>`).
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import React from 'react';
import { act, cleanup, fireEvent, render, waitFor } from '@testing-library/react';

const ONLINE_TOKEN = 'online-tok-xyz';

interface ScriptedResponse {
  data?: unknown;
  error?: unknown;
}

const branchScript: { current: ScriptedResponse } = { current: { data: null, error: null } };

vi.mock('@/lib/supabase-admin', () => ({
  supabaseAdmin: {
    from: () => {
      const chain: Record<string, unknown> = {
        select: () => chain,
        eq: () => chain,
        maybeSingle: () => Promise.resolve(branchScript.current),
      };
      return chain;
    },
  },
}));

vi.mock('next-intl/server', () => ({
  getLocale: async () => 'en',
  getTranslations: async () => (key: string, opts?: Record<string, unknown>) =>
    opts ? `${key}:${JSON.stringify(opts)}` : key,
}));

// Client-side deps pulled in by the real WelcomeFlow.
vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace: vi.fn(), push: vi.fn() }),
}));

vi.mock('@clerk/nextjs', () => ({
  useAuth: () => ({ isSignedIn: false }),
}));

vi.mock('next-intl', () => ({
  useTranslations: () => (key: string, opts?: Record<string, unknown>) =>
    opts ? `${key}:${Object.values(opts).join(',')}` : key,
}));

vi.mock('next/image', () => ({
  default: ({ alt, src }: { alt: string; src: string }) => (
    // eslint-disable-next-line @next/next/no-img-element
    <img alt={alt} src={src} />
  ),
}));

vi.mock('@/contexts/OrganizationContext', () => ({
  useBranding: () => ({ name: 'Chess Empire', logoUrl: null, primaryColor: '#9333ea' }),
  useOrganization: () => ({ org: null, isWhiteLabel: false }),
}));

import WelcomePage from '../page';

const ONLINE_ROW = {
  organization_id: 'org-1',
  external_branch_id: 'br-online',
  branch_name: 'Онлайн',
  kind: 'online',
  expires_at: null,
  revoked_at: null,
};

interface FetchCall {
  url: string;
  init?: RequestInit;
}

let fetchCalls: FetchCall[];

beforeEach(() => {
  branchScript.current = { data: ONLINE_ROW, error: null };
  fetchCalls = [];
  global.fetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === 'string' ? input : input.toString();
    fetchCalls.push({ url, init });
    return {
      ok: true,
      status: 200,
      json: async () => ({ results: [] }),
    } as unknown as Response;
  });
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.restoreAllMocks();
});

function makeParams(token: string) {
  return { params: Promise.resolve({ branchToken: token }) };
}

async function flushDebounce() {
  // 250 ms search debounce + a small buffer for fetch microtasks.
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 320));
  });
}

describe('welcome/[branchToken] — online-kind token', () => {
  it('renders the roster-search flow (not the retired synthetic flow)', async () => {
    const ui = await WelcomePage(makeParams(ONLINE_TOKEN));
    const { container, getByRole } = render(ui);
    // A branch-name heading + a search box are proof this is WelcomeFlow, not
    // the old auto-register interstitial.
    expect(getByRole('heading').textContent).toContain('Онлайн');
    expect(container.querySelector('#welcome-search')).not.toBeNull();
  });

  it('scopes the roster search to the online branch token', async () => {
    const ui = await WelcomePage(makeParams(ONLINE_TOKEN));
    const { container } = render(ui);
    const input = container.querySelector('#welcome-search') as HTMLInputElement;
    fireEvent.change(input, { target: { value: 'ai' } });
    await flushDebounce();
    await waitFor(() => expect(fetchCalls.length).toBeGreaterThan(0));
    expect(fetchCalls[0].url).toContain('/api/chess-empire/students/search');
    expect(fetchCalls[0].url).toContain(`branchToken=${ONLINE_TOKEN}`);
  });
});
