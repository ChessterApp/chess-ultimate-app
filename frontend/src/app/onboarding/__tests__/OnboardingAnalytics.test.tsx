/**
 * @vitest-environment jsdom
 *
 * Onboarding funnel analytics (tracking plan §4 A).
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import React from 'react';
import { cleanup, render, fireEvent, act } from '@testing-library/react';

vi.mock('next-intl', () => ({
  useTranslations: () => {
    const t = (k: string) => k;
    (t as any).has = () => false;
    return t;
  },
  useLocale: () => 'en',
}));

const { routerPush } = vi.hoisted(() => ({ routerPush: vi.fn() }));
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: routerPush, replace: vi.fn() }),
}));
vi.mock('@/lib/onboarding/GameDataContext', () => ({
  useGameData: () => ({ gameData: null, fetchGames: vi.fn(), isLoading: false }),
}));
vi.mock('@/components/LanguageSwitcher', () => ({ default: () => null }));

const trackMock = vi.hoisted(() => vi.fn());
vi.mock('@/lib/analytics/events', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/analytics/events')>()),
  track: trackMock,
}));

import OnboardingPage from '../page';
import { PENDING_ANSWERS_KEY } from '@/lib/onboarding/pendingAnswers';

const COMPLETED_ANSWERS = {
  attribution: 'friend',
  experience: 'beginner',
  platform: 'none',
  platformUsername: '',
  focusAreas: ['tactics'],
  challenge: 'blunder',
  practiceTime: '5min',
  goal: 'beatFriends',
  timeline: '1month',
  noRating: true,
};

function flushAnimation() {
  act(() => {
    vi.runAllTimers();
  });
}

const calls = (event: string) => trackMock.mock.calls.filter((c) => c[0] === event).map((c) => c[1]);

describe('Onboarding analytics', () => {
  beforeEach(() => {
    trackMock.mockReset();
    routerPush.mockReset();
    window.sessionStorage.clear();
    window.localStorage.clear();
    window.history.replaceState(null, '', '/onboarding');
    vi.useFakeTimers();
    vi.stubGlobal('requestAnimationFrame', (cb: FrameRequestCallback) =>
      setTimeout(() => cb(0), 0) as unknown as number,
    );
  });

  afterEach(() => {
    cleanup();
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it('fires onboarding_started on Get started and step_completed with enum buckets', () => {
    const { getByText } = render(<OnboardingPage />);
    flushAnimation();

    fireEvent.click(getByText('welcome.getStarted'));
    expect(calls('onboarding_started')).toEqual([{ entry: 'direct' }]);
    flushAnimation();
    expect(calls('onboarding_step_completed')).toEqual([{ step_index: 1, step_name: 'welcome' }]);

    fireEvent.click(getByText('attribution.socialMedia'));
    flushAnimation();
    expect(calls('onboarding_step_completed')[1]).toEqual({
      step_index: 2,
      step_name: 'attribution',
      answer_bucket: 'socialMedia',
    });
  });

  it('restoring a deep link does not fire step_completed', () => {
    window.sessionStorage.setItem('chesster_onboarding_answers', JSON.stringify(COMPLETED_ANSWERS));
    window.history.replaceState(null, '', '/onboarding?step=16');
    render(<OnboardingPage />);
    flushAnimation();
    expect(trackMock).not.toHaveBeenCalled();
  });

  it('custom-plan continue is enabled with no checkbox, fires completed and hands off to signup', () => {
    window.sessionStorage.setItem('chesster_onboarding_answers', JSON.stringify(COMPLETED_ANSWERS));
    window.history.replaceState(null, '', '/onboarding?step=16');
    const { getByText, queryByRole } = render(<OnboardingPage />);
    flushAnimation();

    expect(queryByRole('checkbox')).toBeNull();
    const start = getByText('customPlan.startFree') as HTMLButtonElement;
    expect(start.disabled).toBe(false);
    fireEvent.click(start);

    expect(trackMock.mock.calls.map((c) => c[0])).toEqual(['onboarding_step_completed', 'onboarding_completed']);
    expect(calls('onboarding_completed')).toEqual([
      { starting_level: 1, skill_tier: 'beginner', goal: 'beatFriends' },
    ]);
    expect(calls('onboarding_step_completed')).toEqual([{ step_index: 16, step_name: 'custom_plan' }]);
    const pending = JSON.parse(window.localStorage.getItem(PENDING_ANSWERS_KEY)!);
    expect(pending).toMatchObject({ experience: 'beginner', goal: 'beatFriends' });
    expect(routerPush).toHaveBeenCalledWith('/sign-up?redirect_url=%2Fonboarding%2Fcomplete');
  });
});
