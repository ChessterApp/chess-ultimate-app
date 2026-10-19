/**
 * @vitest-environment jsdom
 */
import { describe, it, expect, vi, afterEach } from 'vitest';
import { cleanup, render, screen, waitFor } from '@testing-library/react';

vi.mock('next-intl', () => {
  const t = (k: string, v?: Record<string, unknown>) => (v ? `${k}:${JSON.stringify(v)}` : k);
  return { useTranslations: () => t, useLocale: () => 'en' };
});
vi.mock('../TugBoard', () => ({ default: () => <div data-testid="tug-board" /> }));
vi.mock('../RopeScene', () => ({ default: () => <div data-testid="rope-scene" /> }));
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

import MatchScreen from '../MatchScreen';
import ArenaMatch, { type ArenaMatchProps } from '../ArenaMatch';
import { ropePercent } from '../ArenaRope';
import { gameReducer, initialState, currentPuzzle, ROPE_LIMIT, type GameState } from '@/lib/tug-of-war/gameReducer';
import { botLevel } from '@/lib/tug-of-war/bot';
import type { TugPuzzle } from '@/lib/tug-of-war/types';

afterEach(() => {
  cleanup();
  // @ts-expect-error — restore jsdom's default (no matchMedia)
  delete window.matchMedia;
});

const puzzle = (id: string): TugPuzzle => ({
  id,
  fen: 'rnbk1r2/ppppn3/6pB/b3P3/3P4/2P5/PP4PP/RN3RK1 w - - 0 15',
  moves: ['f1f8'],
  rating: 900,
  themes: [],
});

const match = (): GameState =>
  gameReducer(initialState(), {
    type: 'START_MATCH',
    teamAName: 'You',
    teamBName: 'Master Zebra',
    queueA: [puzzle('a1'), puzzle('a2')],
    queueB: [puzzle('b1'), puzzle('b2')],
  });

const arenaProps = (state: GameState, over: Partial<ArenaMatchProps> = {}): ArenaMatchProps => ({
  state,
  bot: botLevel('master'),
  botName: 'Master Zebra',
  botView: { fen: puzzle('b1').fen, thinking: false },
  puzzleA: currentPuzzle(state.boardA),
  puzzleB: currentPuzzle(state.boardB),
  feedbackA: 'idle',
  feedbackB: 'idle',
  skipToast: { A: false, B: false },
  handlersA: { onSolved: vi.fn(), onWrong: vi.fn() },
  remainingMs: 300_000,
  muted: false,
  onToggleMute: vi.fn(),
  onRematch: vi.fn(),
  ...over,
});

function mockViewport(mdUp: boolean) {
  Object.defineProperty(window, 'matchMedia', {
    configurable: true,
    writable: true,
    value: (query: string) => ({
      matches: mdUp,
      media: query,
      addEventListener: () => {},
      removeEventListener: () => {},
    }),
  });
}

describe('MatchScreen — Arena layout routing', () => {
  it('renders the Arena for a bot match at md+, without RopeScene', () => {
    mockViewport(true);
    render(<MatchScreen state={match()} dispatch={vi.fn()} bot={botLevel('master')} />);
    expect(screen.getByTestId('tug-arena')).toBeTruthy();
    expect(screen.queryByTestId('rope-scene')).toBeNull();
    expect(screen.getAllByTestId('tug-board')).toHaveLength(1);
    expect(screen.getByTestId('tug-bot-board')).toBeTruthy();
    expect(screen.getByTestId('tug-bot-rank').textContent).toBe('Master Zebra');
    expect(screen.getByText('5:00')).toBeTruthy();
  });

  it('keeps Team vs Team on the classic layout with RopeScene', () => {
    mockViewport(true);
    render(<MatchScreen state={match()} dispatch={vi.fn()} />);
    expect(screen.queryByTestId('tug-arena')).toBeNull();
    expect(screen.getByTestId('rope-scene')).toBeTruthy();
    expect(screen.getAllByTestId('tug-board')).toHaveLength(2);
  });

  it('keeps the mobile bot layout below md', () => {
    mockViewport(false);
    render(<MatchScreen state={match()} dispatch={vi.fn()} bot={botLevel('master')} />);
    expect(screen.queryByTestId('tug-arena')).toBeNull();
    expect(screen.getByTestId('tug-bot-rank')).toBeTruthy();
  });
});

describe('ArenaMatch', () => {
  it('draws one rope tick per step and places the knot from the rope', () => {
    const { rerender } = render(<ArenaMatch {...arenaProps(match())} />);
    expect(screen.getAllByTestId('tug-rope-tick')).toHaveLength(2 * ROPE_LIMIT + 1);
    const knot = () => screen.getByTestId('tug-rope-knot');
    expect(knot().getAttribute('data-rope')).toBe('0');
    expect(knot().style.left).toBe('50%');

    rerender(<ArenaMatch {...arenaProps({ ...match(), rope: 2 })} />);
    expect(knot().getAttribute('data-rope')).toBe('2');
  });

  it('maps positive rope toward the player (left)', () => {
    expect(ropePercent(ROPE_LIMIT)).toBe(0);
    expect(ropePercent(-ROPE_LIMIT)).toBe(100);
    expect(ropePercent(0)).toBe(50);
    expect(ropePercent(1)).toBeLessThan(50);
  });

  it('flashes "Zebra missed" on a bot wrong move, then hides it', async () => {
    const state = match();
    const { rerender } = render(<ArenaMatch {...arenaProps(state)} />);
    expect(screen.queryByTestId('tug-zebra-missed')).toBeNull();
    rerender(<ArenaMatch {...arenaProps(state, { feedbackB: 'wrong' })} />);
    expect(screen.getByTestId('tug-zebra-missed').textContent).toBe('bot.zebraMissed');
    rerender(<ArenaMatch {...arenaProps(state, { feedbackB: 'idle' })} />);
    await waitFor(() => expect(screen.queryByTestId('tug-zebra-missed')).toBeNull(), { timeout: 3000 });
  });

  it('shows the thinking ring while the zebra thinks', () => {
    render(<ArenaMatch {...arenaProps(match(), { botView: { fen: puzzle('b1').fen, thinking: true } })} />);
    expect(screen.getByTestId('tug-arena-thinking-ring')).toBeTruthy();
    expect(screen.getByText('bot.zebraThinking')).toBeTruthy();
  });

  it('renders the end card inside the Arena', () => {
    const lost: GameState = { ...match(), phase: 'over', winner: 'B', rope: -ROPE_LIMIT };
    render(<ArenaMatch {...arenaProps(lost)} />);
    const card = screen.getByTestId('tug-arena-result');
    expect(screen.getByTestId('tug-arena').contains(card)).toBe(true);
    expect(card.textContent).toContain('bot.botWins');
    expect(card.textContent).toContain('bot.tryAgain');
    expect(card.textContent).toContain('rematch');
  });
});
