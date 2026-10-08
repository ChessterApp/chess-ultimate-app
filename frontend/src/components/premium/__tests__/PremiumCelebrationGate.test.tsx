/**
 * @vitest-environment jsdom
 *
 * Gate logic for the one-time premium welcome ceremony. The heavy
 * PremiumCelebration child (confetti/canvas) is mocked to a lightweight stub so
 * these tests focus purely on the show-once decision and the dismiss write.
 *
 * Covers: shows when active+unseen, hidden when seen, hidden when inactive,
 * hidden on fetch error, and marks seen (POST) on dismiss.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import React from 'react';
import { cleanup, render, screen, fireEvent, waitFor } from '@testing-library/react';

const userStore: { isLoaded: boolean; isSignedIn: boolean; email: string } = {
  isLoaded: true,
  isSignedIn: true,
  email: 'member@example.com',
};
vi.mock('@clerk/nextjs', () => ({
  useUser: () => ({
    isLoaded: userStore.isLoaded,
    isSignedIn: userStore.isSignedIn,
    user: { primaryEmailAddress: { emailAddress: userStore.email } },
  }),
}));

// Stub the ceremony: render the props we care about and expose a dismiss hook.
vi.mock('../PremiumCelebration', () => ({
  default: ({
    email,
    planLabel,
    accessUntil,
    onDismiss,
  }: {
    email: string;
    planLabel: string;
    accessUntil: string | null;
    onDismiss: () => void;
  }) => (
    <div data-testid="ceremony">
      <span data-testid="email">{email}</span>
      <span data-testid="plan">{planLabel}</span>
      <span data-testid="access">{String(accessUntil)}</span>
      <button onClick={onDismiss}>dismiss</button>
    </div>
  ),
}));

import PremiumCelebrationGate, { planLabel } from '../PremiumCelebrationGate';

type FetchResult = { ok: boolean; body: unknown };
const routes: Record<string, FetchResult> = {};
const postSpy = vi.fn();

function jsonRes(r: FetchResult) {
  return Promise.resolve({ ok: r.ok, json: async () => r.body });
}

beforeEach(() => {
  userStore.isLoaded = true;
  userStore.isSignedIn = true;
  userStore.email = 'member@example.com';
  postSpy.mockClear();
  routes['/api/subscription/status'] = {
    ok: true,
    body: { active: true, plan: 'yearly', currentPeriodEnd: '2027-10-08' },
  };
  routes['/api/premium-welcome'] = { ok: true, body: { seen: false } };

  global.fetch = vi.fn((url: string, init?: RequestInit) => {
    if (init?.method === 'POST') {
      postSpy(url);
      return jsonRes({ ok: true, body: { ok: true } });
    }
    return jsonRes(routes[url] ?? { ok: false, body: {} });
  }) as unknown as typeof fetch;
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe('planLabel', () => {
  it('maps yearly/monthly/lifetime and falls back gracefully', () => {
    expect(planLabel('yearly')).toBe('Yearly · all features');
    expect(planLabel('annual_pro')).toBe('Yearly · all features');
    expect(planLabel('monthly')).toBe('Monthly · all features');
    expect(planLabel('lifetime')).toBe('Lifetime · all features');
    expect(planLabel('comp')).toBe('comp · all features');
    expect(planLabel(null)).toBe('Premium · all features');
  });
});

describe('PremiumCelebrationGate', () => {
  it('shows the ceremony when active and unseen', async () => {
    render(<PremiumCelebrationGate />);
    await waitFor(() => expect(screen.getByTestId('ceremony')).toBeTruthy());
    expect(screen.getByTestId('email').textContent).toBe('member@example.com');
    expect(screen.getByTestId('plan').textContent).toBe('Yearly · all features');
    expect(screen.getByTestId('access').textContent).toBe('2027-10-08');
  });

  it('stays hidden when already seen', async () => {
    routes['/api/premium-welcome'] = { ok: true, body: { seen: true } };
    render(<PremiumCelebrationGate />);
    // Give the effect a chance to resolve, then assert nothing rendered.
    await new Promise((r) => setTimeout(r, 0));
    expect(screen.queryByTestId('ceremony')).toBeNull();
  });

  it('stays hidden when the subscription is inactive', async () => {
    routes['/api/subscription/status'] = {
      ok: true,
      body: { active: false, plan: null, currentPeriodEnd: null },
    };
    render(<PremiumCelebrationGate />);
    await new Promise((r) => setTimeout(r, 0));
    expect(screen.queryByTestId('ceremony')).toBeNull();
  });

  it('stays hidden on a fetch error', async () => {
    global.fetch = vi.fn(() =>
      Promise.reject(new Error('network')),
    ) as unknown as typeof fetch;
    render(<PremiumCelebrationGate />);
    await new Promise((r) => setTimeout(r, 0));
    expect(screen.queryByTestId('ceremony')).toBeNull();
  });

  it('stays hidden when a response is not ok', async () => {
    routes['/api/premium-welcome'] = { ok: false, body: {} };
    render(<PremiumCelebrationGate />);
    await new Promise((r) => setTimeout(r, 0));
    expect(screen.queryByTestId('ceremony')).toBeNull();
  });

  it('does nothing when signed out', async () => {
    userStore.isSignedIn = false;
    render(<PremiumCelebrationGate />);
    await new Promise((r) => setTimeout(r, 0));
    expect(screen.queryByTestId('ceremony')).toBeNull();
    expect(global.fetch).not.toHaveBeenCalled();
  });

  it('marks seen (POSTs) and unmounts on dismiss', async () => {
    render(<PremiumCelebrationGate />);
    await waitFor(() => expect(screen.getByTestId('ceremony')).toBeTruthy());
    fireEvent.click(screen.getByText('dismiss'));
    expect(screen.queryByTestId('ceremony')).toBeNull();
    expect(postSpy).toHaveBeenCalledWith('/api/premium-welcome');
  });
});
