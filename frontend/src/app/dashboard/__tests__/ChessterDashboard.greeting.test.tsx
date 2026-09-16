/**
 * @vitest-environment jsdom
 *
 * The dashboard greeting is time-of-day dependent (`new Date().getHours()`).
 * Computing it during SSR (UTC) and again on the client (local timezone) caused
 * a hydration mismatch (React #418). The fix defers all time-dependent output
 * until after mount: the greeting is time-agnostic on the first render and only
 * gains the morning/afternoon/evening word once mounted. These tests confirm the
 * mounted path still produces the correct time-aware greeting.
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

// Echo the key back, except the greeting words which we assert on.
vi.mock('next-intl', () => ({
  useTranslations: () => (key: string) => {
    const map: Record<string, string> = {
      'mascot.greeting.morning': 'Good morning',
      'mascot.greeting.afternoon': 'Good afternoon',
      'mascot.greeting.evening': 'Good evening',
    };
    return map[key] ?? key;
  },
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

vi.mock('@/hooks/useLessonCompletions', () => ({
  useLessonCompletions: () => ({
    completions: { total_completions: 0, completion_dates: [] },
  }),
}));

vi.mock('@/components/LoadingScreen', () => ({
  __esModule: true,
  default: () => <div data-testid="loading" />,
}));

vi.mock('@/components/gamification/StreakBanner', () => ({
  StreakBanner: () => <div />,
  StreakMini: () => <div />,
}));
vi.mock('@/components/gamification/XPDisplay', () => ({
  XPDisplay: () => <div />,
}));
vi.mock('@/components/gamification/LessonPath', () => ({
  LessonPath: () => <div />,
}));
vi.mock('@/components/mascot/SpeechBubble', () => ({
  SpeechBubble: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

import ChessterDashboard from '../ChessterDashboard';

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn(async () => ({ ok: false, json: async () => null })));
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

// The time-aware word the component should show for the current local hour.
function expectedWord(hour: number): string {
  if (hour < 12) return 'Good morning';
  if (hour < 18) return 'Good afternoon';
  return 'Good evening';
}

describe('ChessterDashboard — greeting (hydration-safe)', () => {
  it('renders a time-aware greeting with the user name after mount', async () => {
    const word = expectedWord(new Date().getHours());
    const { findByRole } = render(<ChessterDashboard />);
    const heading = await findByRole('heading', { level: 1 });
    await waitFor(() =>
      expect(heading.textContent).toBe(`${word}, Test!`),
    );
  });

  it('never leaves the greeting on the SSR-safe fallback once mounted', async () => {
    // The mounted greeting always carries a "Good <time>" word; the bare-name
    // fallback ("Test!") is only for the pre-mount / SSR render.
    const { findByRole } = render(<ChessterDashboard />);
    const heading = await findByRole('heading', { level: 1 });
    await waitFor(() => expect(heading.textContent).toContain('Good '));
    expect(heading.textContent).toContain('Test!');
  });
});
