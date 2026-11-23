// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, fireEvent, cleanup } from '@testing-library/react';
import React, { useEffect } from 'react';

// Stand-in board: reports a fresh (unrevealed) state on mount and exposes a
// button that reports the hint as revealed, like pressing Hint does.
const boardProps: any[] = [];
vi.mock('@/components/chess', () => ({
  AnimatedChessBoard: (props: any) => {
    boardProps.push(props);
    const report = (hintRevealed: boolean) =>
      props.onBoardStateChange({ currentFen: props.fen, attempts: 0, solved: false, hintRevealed });
    useEffect(() => report(false), []); // eslint-disable-line react-hooks/exhaustive-deps
    return <button onClick={() => report(true)}>reveal</button>;
  },
  PuzzleSequence: () => null,
}));
vi.mock('@clerk/nextjs', () => ({
  useAuth: () => ({ getToken: async () => 'tok', isSignedIn: true, isLoaded: true }),
  SignInButton: ({ children }: any) => children,
}));
vi.mock('next/navigation', () => ({
  useParams: () => ({ courseSlug: 'basics', lessonSlug: 'rook' }),
  useRouter: () => ({ push: vi.fn() }),
}));
vi.mock('next-intl', () => ({ useTranslations: () => (k: string) => k, useLocale: () => 'en' }));
vi.mock('@/components/ToastProvider', () => ({ useToast: () => ({ showToast: vi.fn() }) }));
vi.mock('@/components/providers/MembershipProvider', () => ({ useMembership: () => ({ policy: null }) }));
vi.mock('@/components/mascot/SpeechBubble', () => ({ InlineTip: ({ message }: { message: string }) => <p>{message}</p> }));
vi.mock('@/components/gamification/XPDisplay', () => ({ XPGain: () => null }));
vi.mock('@/components/gamification/CelebrationOverlay', () => ({ CelebrationOverlay: () => null, QuickCelebration: () => null }));
vi.mock('@/components/empire/LevelCompleteConversion', () => ({ default: () => null }));
vi.mock('@/components/coach/cards/MiniBoard', () => ({ default: () => null }));
vi.mock('@/components/Breadcrumbs', () => ({ default: () => null }));
vi.mock('@/components/LoadingScreen', () => ({ default: () => <p>loading</p> }));

const LESSON = {
  id: 'l1', title: 'Rook', content: 'Move the rook', lesson_type: 'exercise', slug: 'rook',
  course_slug: 'basics', course_title: 'Basics', course_level: 'beginner', progress_status: 'in_progress',
  exercise_fen: '4k3/8/8/8/8/8/8/R3K3 w - - 0 1', solution_move: 'a1a8', exercise_type: 'one_move_puzzle',
  hint_text: 'Slide all the way up', success_message: null, exercise_solution: { arrow: { from: 'a1', path: [] } },
  has_multiple_puzzles: false, puzzle_count: null,
};
vi.mock('@/lib/api', () => ({
  apiFetch: vi.fn(async (url: string) => (url.includes('/chat') ? { messages: [] } : url.includes('/progress') ? {} : LESSON)),
  ApiError: class ApiError extends Error {},
}));

import LessonPage from '../page';

afterEach(() => {
  cleanup();
  boardProps.length = 0;
});

describe('Lesson page single-exercise hint text', () => {
  it('renders hint_text only after the board reports the hint revealed', async () => {
    render(<LessonPage />);
    await screen.findByText('reveal');
    expect(screen.queryByText('Slide all the way up')).toBeNull();
    expect(boardProps.at(-1)).toMatchObject({ revealHintsOnRequest: true, showLegalDests: true });

    fireEvent.click(screen.getByText('reveal'));
    expect(screen.getByText('Slide all the way up')).toBeTruthy();
  });
});
