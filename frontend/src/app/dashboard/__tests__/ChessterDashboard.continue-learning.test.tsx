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
  useLocale: () => 'en',
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

// Configurable per test: XP is derived from total_completions, and the Continue
// Learning card's headline count must match this exact number.
let totalCompletions = 0;
vi.mock('@/hooks/useLessonCompletions', () => ({
  useLessonCompletions: () => ({
    completions: { total_completions: totalCompletions, completion_dates: [] },
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
import { apiFetch } from '@/lib/api';

beforeEach(() => {
  refetch.mockReset();
  totalCompletions = 0;
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

  it('renders overall progress (matching XP) once loaded successfully', async () => {
    totalCompletions = 5; // XP source: 5 lessons completed
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

  // Regression for the reported bug: a user who finished whole courses but has not
  // started the NEXT course must not see that next course's "0 / 37" fraction next
  // to a large XP total. The card must show OVERALL progress that matches XP.
  it('shows aggregate progress matching XP, not the next unstarted course fraction', async () => {
    vi.mocked(apiFetch).mockResolvedValue([
      { id: 'basics', slug: 'basics', title: 'Chess Basics', level: 'beginner', order_index: 0 },
      { id: 'tactics', slug: 'tactics', title: 'Chess Tactics', level: 'beginner', order_index: 1 },
      { id: 'mate3', slug: 'mate3', title: 'Mate in 3 Moves', level: 'intermediate', order_index: 2 },
    ] as never);
    totalCompletions = 77; // 40 + 37 completed lessons → XP source
    progressReturn = {
      courseProgress: {
        basics: { courseId: 'basics', completedLessons: 40, totalLessons: 40, progress: 100 },
        tactics: { courseId: 'tactics', completedLessons: 37, totalLessons: 37, progress: 100 },
        mate3: { courseId: 'mate3', completedLessons: 0, totalLessons: 37, progress: 0 },
      },
      loading: false,
      error: null,
      refetch,
    };
    const { findByTestId } = render(<ChessterDashboard />);

    const card = await findByTestId('continue-learning');
    // Aggregate: 77 completed of 114 total → matches XP (77 lessons), 68%.
    expect(card.textContent).toContain('77 / 114');
    expect(card.textContent).toContain('68%');
    // The misleading next-course fraction must NOT appear.
    expect(card.textContent).not.toContain('0 / 37');
  });
});
