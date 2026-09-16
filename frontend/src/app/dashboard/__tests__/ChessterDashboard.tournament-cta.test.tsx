/**
 * @vitest-environment jsdom
 *
 * The generic Chesster dashboard is the surface chess-empire students land on
 * when they have no personalized CE home — frozen / revoked / no-membership
 * members on the tenant host. The tournament CTA must render there when (and
 * only when) `showTournamentCta` is set, and must never depend on tournament
 * data. On every other host the prop is absent and the banner stays hidden.
 */
import { describe, it, expect, afterEach, vi } from 'vitest';
import { cleanup, render, waitFor } from '@testing-library/react';

vi.mock('@clerk/nextjs', () => ({
  useAuth: () => ({ getToken: async () => 'tok', isSignedIn: false, isLoaded: true }),
  useUser: () => ({ user: { firstName: 'Test' } }),
}));

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }),
}));

// key => key for both the dashboard namespace and the banner's 'empire' one.
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

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe('ChessterDashboard — tournament CTA', () => {
  it('renders the tournament CTA linking to /tournaments when showTournamentCta is set', async () => {
    const { findByTestId } = render(<ChessterDashboard showTournamentCta />);
    const banner = await findByTestId('empire-tournament-cta');
    expect(banner.getAttribute('href')).toBe('/tournaments');
  });

  it('omits the tournament CTA on the generic (non-tenant) dashboard', async () => {
    const { queryByTestId, findByText } = render(<ChessterDashboard />);
    // Wait for the loading state to clear so the CTA would have mounted if present.
    await findByText('dashboard.quickActions');
    await waitFor(() =>
      expect(queryByTestId('empire-tournament-cta')).toBeNull(),
    );
  });
});
