/**
 * @vitest-environment jsdom
 */
import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';

vi.mock('next-intl', () => {
  const t = (k: string, v?: Record<string, unknown>) => (v ? `${k}:${JSON.stringify(v)}` : k);
  t.raw = () => [];
  return { useTranslations: () => t, useLocale: () => 'en' };
});
vi.mock('@/components/LanguageSwitcher', () => ({ default: () => null }));
vi.mock('../TugBoard', () => ({ default: () => <div data-testid="tug-board" /> }));
vi.mock('../RopeScene', () => ({ default: () => null }));
vi.mock('../BotBoard', () => ({ default: () => <div data-testid="tug-bot-board" /> }));
vi.mock('@/lib/tug-of-war/sound', () => ({
  TugSound: class {
    win() {}
    setMuted() {}
    unlock() {
      return true;
    }
  },
  loadMuted: () => true,
  saveMuted: () => {},
}));
vi.mock('@/lib/tug-of-war/confetti', () => ({
  fireWinConfetti: async () => {},
  resetConfetti: async () => {},
}));
const trackMock = vi.hoisted(() => vi.fn());
vi.mock('@/lib/analytics/events', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/analytics/events')>()),
  track: trackMock,
}));

import SetupScreen from '../SetupScreen';
import MatchScreen from '../MatchScreen';
import { gameReducer, initialState, type GameState } from '@/lib/tug-of-war/gameReducer';
import {
  adaptiveReducer,
  initialAdaptive,
  ladderBotLevel,
  saveAdaptive,
  targetRating,
  STORAGE_KEY,
  type AdaptiveState,
  type SavedAdaptive,
} from '@/lib/tug-of-war/adaptive';
import type { AdaptiveView } from '@/lib/tug-of-war/useAdaptiveBot';
import type { TugPuzzle } from '@/lib/tug-of-war/types';

beforeEach(() => localStorage.clear());
afterEach(() => {
  cleanup();
  trackMock.mockReset();
});

const puzzle = (id: string): TugPuzzle => ({
  id,
  fen: 'rnbk1r2/ppppn3/6pB/b3P3/3P4/2P5/PP4PP/RN3RK1 w - - 0 15',
  moves: ['f1f8'],
  rating: 900,
  themes: [],
});

const view = (state: AdaptiveState, result: SavedAdaptive | null = null): AdaptiveView => ({
  state,
  bot: ladderBotLevel(state.ladder),
  target: targetRating(state),
  result,
});

describe('SetupScreen — Fixed vs Adaptive', () => {
  const openBot = (onStart = vi.fn()) => {
    render(<SetupScreen initialTeamA="Knights" initialTeamB="Rooks" onStart={onStart} />);
    fireEvent.click(screen.getByRole('radio', { name: /mode.bot.title/ }));
    return onStart;
  };

  it('offers one Adaptive card next to the six fixed ranks', () => {
    openBot();
    expect(screen.getByTestId('zebra-adaptive').textContent).toContain('adaptive.title');
    expect(screen.getByText('bot.fixed')).toBeTruthy();
    expect(screen.getByTestId('zebra-baby')).toBeTruthy();
    expect(screen.queryByText(/adaptive.lastTime/)).toBeNull();
  });

  it('shows the saved estimate from last time', () => {
    saveAdaptive({ estimate: 1340, avgSeconds: 7, peakBotLevel: 'club', date: '2026-10-18T00:00:00Z' });
    expect(localStorage.getItem(STORAGE_KEY)).toBeTruthy();
    openBot();
    expect(screen.getByText('adaptive.lastTime:{"rating":1340}')).toBeTruthy();
  });

  it('starts an adaptive match on tap', () => {
    const onStart = openBot();
    fireEvent.click(screen.getByTestId('zebra-adaptive'));
    expect(onStart).toHaveBeenCalledWith(expect.objectContaining({ teamA: 'bot.you', adaptive: true }));
    expect(onStart.mock.calls[0][0].bot).toBeUndefined();
  });
});

describe('MatchScreen — adaptive', () => {
  const match = (): GameState =>
    gameReducer(initialState(), {
      type: 'START_MATCH',
      teamAName: 'You',
      teamBName: 'Chesster',
      queueA: [puzzle('a1')],
      queueB: [puzzle('b1')],
    });

  it('renders the level meter next to the badge, named after the live rank', () => {
    const climbed = [1, 2, 3].reduce(
      (s) => adaptiveReducer(s, { type: 'HUMAN_SOLVED', puzzleRating: 900, seconds: 5 }),
      initialAdaptive(),
    ); // 700 → 1000: Club, trend up
    const v = view(climbed);
    render(<MatchScreen state={match()} dispatch={vi.fn()} bot={v.bot} adaptive={v} />);
    const meter = screen.getByTestId('tug-level-meter');
    expect(meter.textContent).toContain('adaptive.level:{"level":3}');
    expect(meter.textContent).toContain('↑');
    expect(screen.getByTestId('tug-bot-rank').textContent).toBe('bot.levels.club');
  });

  it('shows no meter in static bot mode', () => {
    render(<MatchScreen state={match()} dispatch={vi.fn()} bot={ladderBotLevel(initialAdaptive().ladder)} />);
    expect(screen.queryByTestId('tug-level-meter')).toBeNull();
  });

  it('ends with the estimate, speed and peak rank, Rematch and Try fixed level', () => {
    const s = adaptiveReducer(initialAdaptive(), { type: 'HUMAN_SOLVED', puzzleRating: 900, seconds: 7 });
    const result: SavedAdaptive = { estimate: 1340, avgSeconds: 7, peakBotLevel: 'junior', date: '' };
    const onRematch = vi.fn();
    const onTryFixed = vi.fn();
    const over: GameState = { ...match(), phase: 'over', winner: 'A', rope: 2 };
    // The final estimate lands one render after the match ends.
    const { rerender } = render(
      <MatchScreen state={over} dispatch={vi.fn()} bot={view(s).bot} adaptive={view(s)} />,
    );
    expect(screen.queryByTestId('tug-adaptive-summary')).toBeNull();
    expect(trackMock).not.toHaveBeenCalledWith('tug_of_war_finished', expect.anything());

    rerender(
      <MatchScreen
        state={over}
        dispatch={vi.fn()}
        bot={view(s).bot}
        adaptive={view(s, result)}
        onRematch={onRematch}
        onTryFixed={onTryFixed}
      />,
    );
    const summary = screen.getByTestId('tug-adaptive-summary').textContent;
    expect(summary).toContain('adaptive.result.level:{"rating":1340}');
    expect(summary).toContain('adaptive.result.speed:{"seconds":7}');
    expect(summary).toContain('adaptive.result.peak:{"rank":"bot.levels.junior"}');
    expect(trackMock).toHaveBeenCalledWith('tug_of_war_finished', {
      winner_side: 'A',
      mode: 'bot',
      botMode: 'adaptive',
      botLevel: 'junior',
      estimate: 1340,
      avgSeconds: 7,
      peakBotLevel: 'junior',
    });

    fireEvent.click(screen.getByText('rematch'));
    expect(onRematch).toHaveBeenCalled();
    fireEvent.click(screen.getByText('adaptive.tryFixed'));
    expect(onTryFixed).toHaveBeenCalled();
  });

  it('says "none yet" when no zebra was beaten', () => {
    const result: SavedAdaptive = { estimate: 880, avgSeconds: null, peakBotLevel: null, date: '' };
    const s = initialAdaptive();
    const over: GameState = { ...match(), phase: 'over', winner: 'B', rope: -5 };
    render(<MatchScreen state={over} dispatch={vi.fn()} bot={view(s).bot} adaptive={view(s, result)} />);
    const summary = screen.getByTestId('tug-adaptive-summary').textContent;
    expect(summary).toContain('adaptive.result.noPeak');
    expect(summary).not.toContain('adaptive.result.speed');
  });
});
