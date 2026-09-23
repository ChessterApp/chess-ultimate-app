/**
 * @vitest-environment jsdom
 */
import React from 'react';
import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, cleanup, fireEvent } from '@testing-library/react';
import { NextIntlClientProvider } from 'next-intl';

import en from '../../../../messages/en.json';
import GamePanel, { GameStartDialog, GAME_STRENGTHS } from '../GamePanel';
import type { GameStateView } from '@/lib/coach/boards-api';

const coach = en.coach;

function wrap(node: React.ReactElement) {
  return render(
    <NextIntlClientProvider locale="en" messages={en as Record<string, unknown>}>
      {node}
    </NextIntlClientProvider>,
  );
}

function view(overrides: Partial<GameStateView> = {}): GameStateView {
  return {
    board_id: 'b1',
    student_color: 'white',
    engine_elo: 1200,
    comment_mode: 'mistakes',
    status: 'playing',
    result: null,
    termination: null,
    winner: null,
    fen: 'start',
    pgn: '',
    ply: 0,
    moves: [],
    student_to_move: true,
    in_check: false,
    student: null,
    engine: null,
    comment_wanted: false,
    ...overrides,
  };
}

afterEach(cleanup);

describe('GameStartDialog', () => {
  it('starts with the chosen colour, strength and comment mode', () => {
    const onStart = vi.fn();
    wrap(<GameStartDialog defaultElo={1234} onStart={onStart} onCancel={vi.fn()} />);
    // nearest offered strength to the profile rating
    expect((screen.getByTestId('game-elo') as HTMLSelectElement).value).toBe('1200');
    expect(GAME_STRENGTHS).toContain(1200);
    fireEvent.click(screen.getByText(coach.colorBlack));
    fireEvent.change(screen.getByTestId('game-elo'), { target: { value: '1800' } });
    fireEvent.change(screen.getByTestId('game-comments'), { target: { value: 'every' } });
    fireEvent.click(screen.getByText(coach.startGame));
    expect(onStart).toHaveBeenCalledWith({ color: 'black', elo: 1800, comment_mode: 'every' });
  });

  it('cancels', () => {
    const onCancel = vi.fn();
    wrap(<GameStartDialog onStart={vi.fn()} onCancel={onCancel} />);
    fireEvent.click(screen.getByText(coach.cancel));
    expect(onCancel).toHaveBeenCalled();
  });
});

describe('GamePanel', () => {
  it('shows whose move it is and the game controls while playing', () => {
    const onHint = vi.fn();
    const onTakeback = vi.fn();
    const onResign = vi.fn();
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    wrap(
      <GamePanel
        game={view({ ply: 2, in_check: true })}
        thinking={false}
        onHint={onHint}
        onTakeback={onTakeback}
        onResign={onResign}
        onReview={vi.fn()}
        onNewGame={vi.fn()}
        onClose={vi.fn()}
      />,
    );
    expect(screen.getByText(/You play white against the coach \(1200\)/)).toBeTruthy();
    expect(screen.getByText(/Your move · Check!/)).toBeTruthy();
    fireEvent.click(screen.getByText(coach.gameHint));
    fireEvent.click(screen.getByText(coach.gameTakeback));
    fireEvent.click(screen.getByText(coach.gameResign));
    expect(onHint).toHaveBeenCalled();
    expect(onTakeback).toHaveBeenCalled();
    expect(onResign).toHaveBeenCalled();
    expect(screen.queryByText(coach.gameReview)).toBeNull();
  });

  it('shows the verdict of the last move with the better one', () => {
    wrap(
      <GamePanel
        game={view({ ply: 3, student: { san: 'h4', uci: 'h2h4', verdict: 'blunder', cp_loss: 350, eval_after: -300, best: 'e4' } })}
        thinking={false}
        onHint={vi.fn()} onTakeback={vi.fn()} onResign={vi.fn()} onReview={vi.fn()} onNewGame={vi.fn()} onClose={vi.fn()}
      />,
    );
    expect(screen.getByTestId('game-verdict').textContent).toBe('h4: blunder, better was e4');
  });

  it('shows the coach thinking and disables the buttons meanwhile', () => {
    wrap(
      <GamePanel
        game={view({ ply: 1, student_to_move: false })}
        thinking
        onHint={vi.fn()} onTakeback={vi.fn()} onResign={vi.fn()} onReview={vi.fn()} onNewGame={vi.fn()} onClose={vi.fn()}
      />,
    );
    expect(screen.getByText(coach.gameCoachThinking)).toBeTruthy();
    expect((screen.getByText(coach.gameHint) as HTMLButtonElement).disabled).toBe(true);
  });

  it('shows the outcome and the review / new game / close controls when finished', () => {
    const onReview = vi.fn();
    const onNewGame = vi.fn();
    const onClose = vi.fn();
    wrap(
      <GamePanel
        game={view({ status: 'finished', result: '0-1', termination: 'checkmate', winner: 'engine', ply: 8 })}
        thinking={false}
        onHint={vi.fn()} onTakeback={vi.fn()} onResign={vi.fn()} onReview={onReview} onNewGame={onNewGame} onClose={onClose}
      />,
    );
    expect(screen.getByText('You lost — checkmate (0-1)')).toBeTruthy();
    fireEvent.click(screen.getByText(coach.gameReview));
    fireEvent.click(screen.getByText(coach.gameNew));
    fireEvent.click(screen.getByText(coach.gameClose));
    expect(onReview).toHaveBeenCalled();
    expect(onNewGame).toHaveBeenCalled();
    expect(onClose).toHaveBeenCalled();
    expect(screen.queryByText(coach.gameResign)).toBeNull();
  });

  it('a draw by stalemate', () => {
    wrap(
      <GamePanel
        game={view({ status: 'finished', result: '1/2-1/2', termination: 'stalemate', winner: null })}
        thinking={false}
        onHint={vi.fn()} onTakeback={vi.fn()} onResign={vi.fn()} onReview={vi.fn()} onNewGame={vi.fn()} onClose={vi.fn()}
      />,
    );
    expect(screen.getByText('Draw — stalemate (1/2-1/2)')).toBeTruthy();
  });
});
