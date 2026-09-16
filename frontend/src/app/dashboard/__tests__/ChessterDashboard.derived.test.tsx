/**
 * @vitest-environment jsdom
 *
 * Non-linked Chesster users have no tournament economy, so the dashboard must
 * derive their XP / rank / streak from lesson completions instead of showing
 * the old hard-coded 0s. Here the gamification profile resolves to unlinked
 * (fetch returns non-ok) and the user has completed lessons — the header XP and
 * streak must reflect the derived values.
 */
import { describe, it, expect, afterEach, beforeEach, vi } from 'vitest';
import { cleanup, render, waitFor } from '@testing-library/react';

vi.mock('@clerk/nextjs', () => ({
  useAuth: () => ({ getToken: async () => 'tok', isSignedIn: true, isLoaded: true }),
  useUser: () => ({ user: { firstName: 'Test' } }),
}));

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }),
}));

vi.mock('next-intl', () => ({
  useTranslations: () => (key: string) => key,
  useLocale: () => 'en',
}));

vi.mock('@/lib/api', () => ({
  apiFetch: vi.fn(async () => []),
  ApiError: class ApiError extends Error {},
}));

vi.mock('@/components/ToastProvider', () => ({
  useToast: () => ({ showToast: vi.fn() }),
}));

vi.mock('@/hooks/useBackendHealth', () => ({
  useBackendHealth: () => true,
}));

vi.mock('@/hooks/useCourseProgress', () => ({
  useCourseProgress: () => ({ courseProgress: {} }),
}));

// User has completed 7 lessons across 3 consecutive days ending today.
const today = new Date().toISOString().slice(0, 10);
const day = (offset: number) => {
  const d = new Date(today + 'T00:00:00Z');
  d.setUTCDate(d.getUTCDate() + offset);
  return d.toISOString().slice(0, 10);
};
vi.mock('@/hooks/useLessonCompletions', () => ({
  useLessonCompletions: () => ({
    completions: {
      total_completions: 7,
      completion_dates: [day(-2), day(-1), day(0)],
    },
  }),
}));

vi.mock('@/components/LoadingScreen', () => ({
  __esModule: true,
  default: () => <div data-testid="loading" />,
}));

// Expose the props we care about instead of the real (styled) widgets.
vi.mock('@/components/gamification/StreakBanner', () => ({
  StreakBanner: ({ streakDays, unit }: { streakDays: number; unit: string }) => (
    <div data-testid="streak-banner" data-unit={unit}>{streakDays}</div>
  ),
  StreakMini: ({ streakDays }: { streakDays: number }) => (
    <div data-testid="streak-mini">{streakDays}</div>
  ),
}));
vi.mock('@/components/gamification/XPDisplay', () => ({
  XPDisplay: ({ xp }: { xp: number }) => <div data-testid="xp-display">{xp}</div>,
}));
vi.mock('@/components/gamification/LessonPath', () => ({
  LessonPath: () => <div />,
}));
vi.mock('@/components/mascot/SpeechBubble', () => ({
  SpeechBubble: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

import ChessterDashboard from '../ChessterDashboard';

beforeEach(() => {
  // Unlinked: /api/gamification/profile responds non-ok → profile stays null.
  vi.stubGlobal('fetch', vi.fn(async () => ({ ok: false, json: async () => null })));
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

describe('ChessterDashboard — derived stats for non-linked users', () => {
  it('renders derived XP (7 lessons × 10) instead of 0', async () => {
    const { findAllByTestId } = render(<ChessterDashboard />);
    const xp = await findAllByTestId('xp-display');
    expect(xp[0].textContent).toBe('70');
  });

  it('renders the derived daily streak (3 consecutive days) instead of 0', async () => {
    const { findByTestId } = render(<ChessterDashboard />);
    const mini = await findByTestId('streak-mini');
    expect(mini.textContent).toBe('3');
  });

  it('labels the non-linked streak in days, not weeks', async () => {
    const { findByTestId } = render(<ChessterDashboard />);
    await waitFor(() =>
      expect(findByTestId('streak-banner')).resolves.toBeTruthy(),
    );
    const banner = await findByTestId('streak-banner');
    expect(banner.getAttribute('data-unit')).toBe('days');
  });
});
