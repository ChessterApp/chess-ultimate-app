/**
 * @vitest-environment jsdom
 *
 * Server-component tests for /welcome/[branchToken]/page.tsx. Mocks the
 * Supabase admin client with a scripted single-row response so we can
 * exercise the valid / not-found / revoked / expired branches.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import React from 'react';
import { cleanup, render } from '@testing-library/react';

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
  getTranslations: async () => (key: string, opts?: Record<string, unknown>) =>
    opts ? `${key}:${JSON.stringify(opts)}` : key,
}));

vi.mock('next/image', () => ({
  default: ({ alt, src }: { alt: string; src: string }) => (
    // eslint-disable-next-line @next/next/no-img-element
    <img alt={alt} src={src} />
  ),
}));

// Stub the client flow so we don't pull in branding context / next-intl client hooks.
vi.mock('../WelcomeFlow', () => ({
  default: ({ branchName, branchToken }: { branchName: string; branchToken: string }) => (
    <div data-testid="welcome-flow" data-branch={branchName} data-token={branchToken} />
  ),
}));

import WelcomePage, { generateMetadata } from '../page';

function makeParams(token: string) {
  return { params: Promise.resolve({ branchToken: token }) };
}

const VALID_TOKEN = {
  organization_id: 'org-1',
  external_branch_id: 'br-1',
  branch_name: 'Debut',
  expires_at: null,
  revoked_at: null,
};

describe('welcome/[branchToken] server page', () => {
  beforeEach(() => {
    branchScript.current = { data: null, error: null };
  });

  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it('renders the welcome flow for a valid token', async () => {
    branchScript.current = { data: VALID_TOKEN, error: null };
    const ui = await WelcomePage(makeParams('good'));
    const { getByTestId } = render(ui);
    const flow = getByTestId('welcome-flow');
    expect(flow.getAttribute('data-branch')).toBe('Debut');
    expect(flow.getAttribute('data-token')).toBe('good');
  });

  it('renders the link-invalid screen when token not found', async () => {
    branchScript.current = { data: null, error: null };
    const ui = await WelcomePage(makeParams('missing'));
    const { container } = render(ui);
    expect(container.textContent).toContain('linkInvalidTitle');
    expect(container.textContent).toContain('linkInvalidBody');
  });

  it('renders the link-invalid screen when token revoked', async () => {
    branchScript.current = {
      data: { ...VALID_TOKEN, revoked_at: '2026-01-01T00:00:00Z' },
      error: null,
    };
    const ui = await WelcomePage(makeParams('revoked'));
    const { container } = render(ui);
    expect(container.textContent).toContain('linkInvalidTitle');
  });

  it('renders the link-invalid screen when token expired', async () => {
    branchScript.current = {
      data: { ...VALID_TOKEN, expires_at: '2020-01-01T00:00:00Z' },
      error: null,
    };
    const ui = await WelcomePage(makeParams('expired'));
    const { container } = render(ui);
    expect(container.textContent).toContain('linkInvalidTitle');
  });

  it('uses branch name in metadata title for valid token', async () => {
    branchScript.current = { data: VALID_TOKEN, error: null };
    const meta = await generateMetadata(makeParams('good'));
    expect(String(meta.title)).toContain('metaTitle');
    expect(String(meta.title)).toContain('Debut');
  });

  it('uses link-invalid title for invalid token metadata', async () => {
    branchScript.current = { data: null, error: null };
    const meta = await generateMetadata(makeParams('missing'));
    expect(String(meta.title)).toContain('linkInvalidTitle');
  });
});
