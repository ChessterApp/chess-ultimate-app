/**
 * @vitest-environment jsdom
 */
import { describe, it, expect, vi, afterEach } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';

vi.mock('next-intl', () => {
  const t = (k: string, v?: Record<string, unknown>) => (v ? `${k}:${JSON.stringify(v)}` : k);
  t.raw = () => [];
  return { useTranslations: () => t, useLocale: () => 'en' };
});
vi.mock('@/components/LanguageSwitcher', () => ({ default: () => null }));
vi.mock('../TugBoard', () => ({ default: () => <div data-testid="tug-board" /> }));
vi.mock('../RopeScene', () => ({ default: () => null }));
vi.mock('../BotBoard', () => ({
  default: ({ fen }: { fen: string }) => <div data-testid="tug-bot-board">{fen}</div>,
}));
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
import { BOT_LEVELS, botLevel } from '@/lib/tug-of-war/bot';
import type { TugPuzzle } from '@/lib/tug-of-war/types';

afterEach(() => {
  cleanup();
  trackMock.mockReset();
});

const puzzle = (id: string): TugPuzzle => ({
  id,
  fen: 'rnbk1r2/ppppn3/6pB/b3P3/3P4/2P5/PP4PP/RN3RK1 w - - 0 15',
  moves: ['f1f8'],
  rating: 513,
  themes: [],
});

describe('SetupScreen — mode choice', () => {
  it('offers Team vs Team and You vs Chesster, team flow first and unchanged', () => {
    const onStart = vi.fn();
    render(<SetupScreen initialTeamA="Knights" initialTeamB="Rooks" onStart={onStart} />);
    expect(screen.getByRole('radio', { name: /mode.team.title/ }).getAttribute('aria-checked')).toBe('true');
    expect(screen.getByRole('radio', { name: /mode.bot.title/ })).toBeTruthy();
    expect(screen.queryByTestId('zebra-baby')).toBeNull();

    fireEvent.click(screen.getByRole('button', { name: 'levels.rook' }));
    fireEvent.click(screen.getByRole('button', { name: 'start' }));
    expect(onStart).toHaveBeenCalledWith({ teamA: 'Knights', teamB: 'Rooks', level: 'rook', themes: [] });
  });

  it('shows six zebra rank cards and starts a bot match on tap', () => {
    const onStart = vi.fn();
    render(<SetupScreen initialTeamA="Knights" initialTeamB="Rooks" onStart={onStart} />);
    fireEvent.click(screen.getByRole('radio', { name: /mode.bot.title/ }));

    for (const l of BOT_LEVELS) expect(screen.getByTestId(`zebra-${l.id}`)).toBeTruthy();
    expect(screen.queryByRole('button', { name: 'start' })).toBeNull();

    fireEvent.click(screen.getByTestId('zebra-expert'));
    expect(onStart).toHaveBeenCalledWith({
      teamA: 'bot.you',
      teamB: 'bot.levels.expert',
      level: 'rook',
      themes: [],
      bot: 'expert',
    });
  });

  it('reopens in bot mode after a bot match', () => {
    render(<SetupScreen initialTeamA="A" initialTeamB="B" onStart={vi.fn()} initialBot="club" />);
    expect(screen.getByRole('radio', { name: /mode.bot.title/ }).getAttribute('aria-checked')).toBe('true');
  });
});

describe('MatchScreen — bot mode', () => {
  const match = (): GameState =>
    gameReducer(initialState(), {
      type: 'START_MATCH',
      teamAName: 'You',
      teamBName: 'Master Zebra',
      queueA: [puzzle('a1'), puzzle('a2')],
      queueB: [puzzle('b1'), puzzle('b2')],
    });

  it('renders one human board, the live bot board and the zebra rank badge', () => {
    render(<MatchScreen state={match()} dispatch={vi.fn()} bot={botLevel('master')} />);
    expect(screen.getAllByTestId('tug-board')).toHaveLength(1);
    expect(screen.getByTestId('tug-bot-board').textContent).toContain(puzzle('b1').fen);
    expect(screen.getByTestId('tug-bot-rank').textContent).toContain('Master Zebra');
    expect(screen.getByText('5:00')).toBeTruthy();
  });

  it('keeps Team vs Team with two human boards and no bot UI', () => {
    render(<MatchScreen state={match()} dispatch={vi.fn()} />);
    expect(screen.getAllByTestId('tug-board')).toHaveLength(2);
    expect(screen.queryByTestId('tug-bot-board')).toBeNull();
    expect(screen.queryByText('5:00')).toBeNull();
  });

  it('shows the bot end screen and tags analytics with the mode and rank', () => {
    const { rerender } = render(
      <MatchScreen state={match()} dispatch={vi.fn()} bot={botLevel('master')} />,
    );
    const lost: GameState = { ...match(), phase: 'over', winner: 'B', rope: -5 };
    rerender(<MatchScreen state={lost} dispatch={vi.fn()} bot={botLevel('master')} />);
    expect(screen.getByText('bot.botWins')).toBeTruthy();
    expect(screen.getByText('bot.tryAgain')).toBeTruthy();
    expect(trackMock).toHaveBeenCalledWith('tug_of_war_finished', {
      winner_side: 'B',
      mode: 'bot',
      botMode: 'static',
      botLevel: 'master',
    });
  });

  it('says "you beat Chesster" with the rank, and calls a time-up draw', () => {
    const won: GameState = { ...match(), phase: 'over', winner: 'A', rope: 2 };
    const { rerender } = render(<MatchScreen state={won} dispatch={vi.fn()} bot={botLevel('master')} />);
    expect(screen.getByText('bot.youWin:{"rank":"Master Zebra"}')).toBeTruthy();
    expect(screen.getByText('bot.timeUp')).toBeTruthy();

    rerender(
      <MatchScreen state={{ ...won, winner: null, rope: 0 }} dispatch={vi.fn()} bot={botLevel('master')} />,
    );
    expect(screen.getByText('bot.draw')).toBeTruthy();
  });
});
