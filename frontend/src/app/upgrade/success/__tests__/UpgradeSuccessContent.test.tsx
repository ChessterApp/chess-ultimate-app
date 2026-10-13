// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import React from 'react';
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import type { ActivationState } from '../pollSubscription';

const { push, track, retry, hookState } = vi.hoisted(() => ({
  push: vi.fn(),
  track: vi.fn(),
  retry: vi.fn(),
  hookState: { current: { phase: 'loading' } as ActivationState },
}));

vi.mock('next-intl', () => ({
  useTranslations: () => (k: string, opts?: Record<string, unknown>) =>
    opts ? `${k}:${JSON.stringify(opts)}` : k,
}));
vi.mock('next/navigation', () => ({ useRouter: () => ({ push }) }));
vi.mock('@/lib/analytics/events', async (orig) => ({
  ...(await orig<typeof import('@/lib/analytics/events')>()),
  track,
}));
vi.mock('../pollSubscription', () => ({
  useSubscriptionActivation: () => ({ state: hookState.current, retry }),
}));

import UpgradeSuccessContent, { SUCCESS_REDIRECT_MS } from '../UpgradeSuccessContent';

describe('UpgradeSuccessContent', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    push.mockClear();
    track.mockClear();
    retry.mockClear();
    hookState.current = { phase: 'loading' };
  });
  afterEach(() => {
    cleanup();
    vi.useRealTimers();
  });

  it('shows the loading state and fires checkout_return_viewed once', () => {
    const { rerender } = render(<UpgradeSuccessContent />);
    rerender(<UpgradeSuccessContent />);
    expect(screen.getByText('loadingTitle')).toBeTruthy();
    expect(track).toHaveBeenCalledTimes(1);
    expect(track).toHaveBeenCalledWith('checkout_return_viewed');
  });

  it('on success shows the plan, tracks activation once and redirects to /learn after 5s', () => {
    const { rerender } = render(<UpgradeSuccessContent />);
    hookState.current = { phase: 'success', plan: 'yearly' };
    rerender(<UpgradeSuccessContent />);
    rerender(<UpgradeSuccessContent />);

    expect(screen.getByText('successTitle')).toBeTruthy();
    expect(screen.getByText(/successPlan/).textContent).toContain('plans.yearly');
    expect(screen.getByRole('link', { name: 'startLearning' }).getAttribute('href')).toBe('/learn');
    expect(track).toHaveBeenCalledWith('subscription_activated_client', { tier: 'yearly' });
    expect(track.mock.calls.filter(([e]) => e === 'subscription_activated_client')).toHaveLength(1);

    act(() => {
      vi.advanceTimersByTime(SUCCESS_REDIRECT_MS - 1);
    });
    expect(push).not.toHaveBeenCalled();
    act(() => {
      vi.advanceTimersByTime(1);
    });
    expect(push).toHaveBeenCalledWith('/learn');
  });

  it('falls back to generic copy for an unknown plan', () => {
    hookState.current = { phase: 'success', plan: 'unknown' };
    render(<UpgradeSuccessContent />);
    expect(screen.getByText('successBody')).toBeTruthy();
  });

  it('on timeout offers retry and a support link', () => {
    hookState.current = { phase: 'timeout' };
    render(<UpgradeSuccessContent />);
    expect(screen.getByText('timeoutTitle')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'retry' }));
    expect(retry).toHaveBeenCalled();
    expect(screen.getByRole('link', { name: 'support@chesster.io' }).getAttribute('href')).toBe(
      'mailto:support@chesster.io',
    );
  });
});
