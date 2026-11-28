// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, fireEvent, cleanup, waitFor } from '@testing-library/react';
import React, { useEffect } from 'react';

// Stand-in board: reports its state on mount, solves on "solve", reveals the
// hint on "reveal", and counts mounts so a remount would show.
const boardMounts = { count: 0 };
vi.mock('@/components/chess', () => ({
  AnimatedChessBoard: (props: any) => {
    useEffect(() => {
      boardMounts.count++;
      props.onBoardStateChange({ currentFen: props.fen, attempts: 0, solved: false, hintRevealed: false });
    }, []); // eslint-disable-line react-hooks/exhaustive-deps
    return (
      <>
        <button onClick={() => props.onCorrectMove()}>solve</button>
        <button onClick={() => props.onBoardStateChange({ currentFen: props.fen, attempts: 1, solved: true, hintRevealed: true })}>reveal</button>
      </>
    );
  },
  PuzzleSequence: () => null,
}));
// Stable like Clerk's: a new getToken each render would re-run the main fetch.
const auth = vi.hoisted(() => ({ getToken: async () => 'tok', isSignedIn: true, isLoaded: true }));
vi.mock('@clerk/nextjs', () => ({
  useAuth: () => auth,
  SignInButton: ({ children }: any) => children,
}));
vi.mock('next/navigation', () => ({
  useParams: () => ({ courseSlug: 'basics', lessonSlug: 'rook' }),
  useRouter: () => ({ push: vi.fn() }),
}));
const localeState = vi.hoisted(() => ({ current: 'en' }));
vi.mock('next-intl', () => ({
  useTranslations: () => (k: string, v?: Record<string, unknown>) => (v ? `${k} ${Object.values(v).join(' ')}` : k),
  useLocale: () => localeState.current,
}));
vi.mock('@/components/ToastProvider', () => ({ useToast: () => ({ showToast: vi.fn() }) }));
vi.mock('@/components/providers/MembershipProvider', () => ({ useMembership: () => ({ policy: null }) }));
vi.mock('@/components/mascot/SpeechBubble', () => ({ InlineTip: ({ message }: { message: string }) => <p>{message}</p> }));
vi.mock('@/components/gamification/XPDisplay', () => ({ XPGain: () => null }));
vi.mock('@/components/gamification/CelebrationOverlay', () => ({ CelebrationOverlay: () => null, QuickCelebration: () => null }));
vi.mock('@/components/empire/LevelCompleteConversion', () => ({ default: () => null }));
vi.mock('@/components/coach/cards/MiniBoard', () => ({ default: () => null }));
vi.mock('@/components/Breadcrumbs', () => ({ default: () => null }));
vi.mock('@/components/LoadingScreen', () => ({ default: () => <p>loading</p> }));

const lessonIn = (locale: string) => ({
  id: 'l1', title: `Rook ${locale}`, content: `Move the rook ${locale}`, lesson_type: 'exercise', slug: 'rook',
  course_slug: 'basics', course_title: `Basics ${locale}`, course_level: 'beginner', progress_status: 'in_progress',
  exercise_fen: '4k3/8/8/8/8/8/8/R3K3 w - - 0 1', solution_move: 'a1a8', exercise_type: 'one_move_puzzle',
  hint_text: `Slide up ${locale}`, success_message: null, exercise_solution: { arrow: { from: 'a1', path: [] } },
  has_multiple_puzzles: false, puzzle_count: null,
});
const { apiFetch } = vi.hoisted(() => ({ apiFetch: vi.fn() }));
vi.mock('@/lib/api', () => ({ apiFetch, ApiError: class ApiError extends Error {} }));

import LessonPage from '../page';

const calls = (part: string, method = 'GET') =>
  apiFetch.mock.calls.filter(([url, opts]) => url.includes(part) && (opts?.method ?? 'GET') === method);
const lessonCalls = () => calls('/api/learn/basics/rook?');

function respond() {
  apiFetch.mockImplementation(async (url: string) => {
    if (url.includes('/chat')) return { messages: [{ role: 'user', content: 'how does the rook move?' }] };
    if (url.includes('/progress')) return {};
    return lessonIn(new URL(url, 'http://x').searchParams.get('locale')!);
  });
}

afterEach(() => {
  cleanup();
  apiFetch.mockReset();
  boardMounts.count = 0;
  localeState.current = 'en';
});

describe('Lesson page language switch', () => {
  it('fetches the lesson once on mount, without a locale refresh', async () => {
    respond();
    render(<LessonPage />);
    await screen.findByText('Rook en');
    await new Promise((r) => setTimeout(r, 20));
    expect(lessonCalls()).toHaveLength(1);
    expect(calls('/progress', 'POST')).toHaveLength(1);
  });

  it('swaps only the text on a locale change, keeping solved/hint/chat/board state', async () => {
    respond();
    const { rerender } = render(<LessonPage />);
    await screen.findByText('Rook en');
    fireEvent.click(screen.getByText('solve'));
    fireEvent.click(screen.getByText('reveal'));
    const complete = () => screen.getByText('lesson.completeLesson').closest('button')!;
    expect(complete().disabled).toBe(false);
    expect(screen.getByText('Slide up en')).toBeTruthy();
    // "in progress" on load + the quiet completion save on solve.
    await waitFor(() => expect(calls('/progress', 'POST')).toHaveLength(2));

    localeState.current = 'ru';
    rerender(<LessonPage />);

    await screen.findByText('Rook ru');
    expect(screen.getByText('Move the rook ru')).toBeTruthy();
    expect(screen.getByText('Slide up ru')).toBeTruthy(); // hint stays revealed
    expect(screen.getByText(/Basics ru/)).toBeTruthy();
    expect(complete().disabled).toBe(false); // exerciseSolved survived
    expect(screen.getByText('how does the rook move?')).toBeTruthy(); // chat kept
    expect(boardMounts.count).toBe(1); // board not remounted
    expect(lessonCalls().map(([url]) => url)).toEqual([
      expect.stringContaining('locale=en'),
      expect.stringContaining('locale=ru'),
    ]);
    expect(calls('/chat')).toHaveLength(1);
    expect(calls('/progress', 'POST')).toHaveLength(2); // no new "in progress"
  });

  it('drops a stale response when the locale moves on before it lands', async () => {
    respond();
    const { rerender } = render(<LessonPage />);
    await screen.findByText('Rook en');

    let releaseRu!: () => void;
    const ruGate = new Promise<void>((r) => { releaseRu = r; });
    apiFetch.mockImplementation(async (url: string) => {
      const locale = new URL(url, 'http://x').searchParams.get('locale')!;
      if (locale === 'ru') await ruGate;
      return lessonIn(locale);
    });

    localeState.current = 'ru';
    rerender(<LessonPage />);
    localeState.current = 'kz';
    rerender(<LessonPage />);
    await screen.findByText('Rook kz');

    releaseRu();
    await new Promise((r) => setTimeout(r, 20));
    expect(screen.getByText('Rook kz')).toBeTruthy();
    expect(screen.queryByText('Rook ru')).toBeNull();
    // Had the ru text landed, the page would have fetched kz a second time.
    expect(lessonCalls().map(([url]) => new URL(url, 'http://x').searchParams.get('locale'))).toEqual(['en', 'ru', 'kz']);
  });
});
