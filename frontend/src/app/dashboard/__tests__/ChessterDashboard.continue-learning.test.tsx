/**
 * @vitest-environment jsdom
 *
 * The Continue Learning card must never silently render progress numbers from a
 * failed or pending fetch. While progress is loading it shows a skeleton; on
 * error it shows a retry affordance (which re-invokes the hook's refetch) and no
 * numbers; only a successful load renders the real progress.
 */
import { describe, it, expect, afterEach, beforeEach, vi } from 'vitest';
import { cleanup, render, fireEvent } from '@testing-library/react';

vi.mock('@clerk/nextjs', () => ({
  useAuth: () => ({ getToken: async () => 'tok', isSignedIn: true, isLoaded: true }),
  useUser: () => ({ user: { firstName: 'Test' } }),
}));

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }),
}));

vi.mock('next-intl', () => ({
  useTranslations: () => (key: string) => key,
}));

// One unlocked, in-progress course so `currentCourse` is defined.
const COURSE = {
  id: 'course-tactics-1',
  slug: 'chess-tactics-1',
  title: 'Chess Tactics 1',
  level: 'beginner',
  order_index: 0,
};
vi.mock('@/lib/api', () => ({
  apiFetch: vi.fn(async () => [COURSE]),
  ApiError: class ApiError extends Error {},
}));

vi.mock('@/components/ToastProvider', () => ({
  useToast: () => ({ showToast: vi.fn() }),
}));

vi.mock('@/hooks/useBackendHealth', () => ({
  useBackendHealth: () => true,
}));

// Configurable per test.
const refetch = vi.fn();
let progressReturn: {
  courseProgress: Record<string, unknown>;
  loading: boolean;
  error: string | null;
  refetch: () => void;
};
vi.mock('@/hooks/useCourseProgress', () => ({
  useCourseProgress: () => progressReturn,
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
  refetch.mockReset();
  vi.stubGlobal('fetch', vi.fn(async () => ({ ok: false, json: async () => null })));
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

describe('ChessterDashboard — Continue Learning fetch states', () => {
  it('shows a loading skeleton while progress is loading', async () => {
    progressReturn = { courseProgress: {}, loading: true, error: null, refetch };
    const { findByTestId, queryByTestId } = render(<ChessterDashboard />);

    expect(await findByTestId('continue-learning-loading')).toBeTruthy();
    expect(queryByTestId('continue-learning-error')).toBeNull();
  });

  it('shows a retry state with no progress numbers on error', async () => {
    progressReturn = { courseProgress: {}, loading: false, error: '503', refetch };
    const { findByTestId, container } = render(<ChessterDashboard />);

    const errorCard = await findByTestId('continue-learning-error');
    expect(errorCard).toBeTruthy();
    // No progress percentage rendered in the error state.
    expect(container.textContent).not.toContain('%');

    const retryBtn = errorCard.querySelector('button')!;
    fireEvent.click(retryBtn);
    expect(refetch).toHaveBeenCalledTimes(1);
  });

  it('renders real progress once loaded successfully', async () => {
    progressReturn = {
      courseProgress: {
        'course-tactics-1': {
          courseId: 'course-tactics-1',
          completedLessons: 5,
          totalLessons: 20,
          progress: 25,
        },
      },
      loading: false,
      error: null,
      refetch,
    };
    const { findByTestId, queryByTestId } = render(<ChessterDashboard />);

    const card = await findByTestId('continue-learning');
    expect(card.textContent).toContain('25%');
    expect(card.textContent).toContain('5 / 20');
    expect(queryByTestId('continue-learning-loading')).toBeNull();
    expect(queryByTestId('continue-learning-error')).toBeNull();
  });
});
