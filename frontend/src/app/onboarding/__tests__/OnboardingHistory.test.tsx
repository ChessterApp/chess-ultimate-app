/**
 * @vitest-environment jsdom
 *
 * Onboarding wizard back-navigation: each step is mirrored to `?step=N`,
 * popstate steps back, a refresh restores step + answers, and an invalid deep
 * link snaps to the earliest incomplete step. The translator echoes keys, so
 * screens are identified by their `<key>.title` text.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import React from 'react';
import { cleanup, render, fireEvent, act } from '@testing-library/react';

vi.mock('next-intl', () => ({
  useTranslations: () => {
    const t = (k: string, opts?: any) => (opts ? `${k}:${JSON.stringify(opts)}` : k);
    (t as any).has = () => false;
    return t;
  },
  useLocale: () => 'en',
}));

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn() }),
}));

vi.mock('@/lib/onboarding/GameDataContext', () => ({
  useGameData: () => ({ gameData: null, fetchGames: vi.fn(), isLoading: false }),
}));

vi.mock('@/components/LanguageSwitcher', () => ({ default: () => null }));

import OnboardingPage from '../page';

const STORAGE_KEY = 'chesster_onboarding_answers';

// Flush the 300ms slide timeout + its rAF idle chain.
function flushAnimation() {
  act(() => {
    vi.runAllTimers();
  });
}

describe('Onboarding wizard URL history sync', () => {
  beforeEach(() => {
    window.sessionStorage.clear();
    window.history.replaceState(null, '', '/onboarding');
    vi.useFakeTimers();
    // Make rAF flushable by the fake timer clock.
    vi.stubGlobal('requestAnimationFrame', (cb: FrameRequestCallback) =>
      setTimeout(() => cb(0), 0) as unknown as number,
    );
  });

  afterEach(() => {
    cleanup();
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it('pushes a ?step entry on Next and steps back on popstate', () => {
    const { getByText, queryByText } = render(<OnboardingPage />);
    flushAnimation(); // mount restore normalizes the base entry

    // Step 1 → Next
    fireEvent.click(getByText('welcome.getStarted'));
    expect(window.location.search).toBe('?step=2');
    flushAnimation();
    expect(queryByText('attribution.title')).toBeTruthy();

    // Browser Back → step 1
    act(() => {
      window.history.replaceState(null, '', '/onboarding?step=1');
      window.dispatchEvent(new PopStateEvent('popstate'));
    });
    flushAnimation();
    expect(queryByText('welcome.getStarted')).toBeTruthy();
  });

  it('normalizes the base entry to ?step=1 on a clean mount', () => {
    render(<OnboardingPage />);
    flushAnimation();
    expect(window.location.search).toBe('?step=1');
  });

  it('snaps an invalid deep link to the earliest incomplete step', () => {
    window.history.replaceState(null, '', '/onboarding?step=12');
    const { queryByText } = render(<OnboardingPage />);
    flushAnimation();

    // No stored answers → earliest incomplete is the attribution step (2).
    expect(window.location.search).toBe('?step=2');
    expect(queryByText('attribution.title')).toBeTruthy();
  });

  it('restores step and answers on refresh from sessionStorage + URL', () => {
    window.sessionStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({
        attribution: 'friend',
        experience: 'beginner',
        platform: 'none',
        platformUsername: '',
        focusAreas: ['tactics'],
        challenge: 'blunder',
        practiceTime: '5min',
        goal: 'beatFriends',
        timeline: '1month',
      }),
    );
    window.history.replaceState(null, '', '/onboarding?step=8');

    const { queryByText } = render(<OnboardingPage />);
    flushAnimation();

    // All gating answers present → step 8 is allowed and preserved.
    expect(window.location.search).toBe('?step=8');
    expect(queryByText('challenge.title')).toBeTruthy();

    // Answers survived the remount (not clobbered by defaults).
    const persisted = JSON.parse(window.sessionStorage.getItem(STORAGE_KEY) || '{}');
    expect(persisted.attribution).toBe('friend');
    expect(persisted.focusAreas).toEqual(['tactics']);
  });
});
