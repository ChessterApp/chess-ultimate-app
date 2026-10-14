/**
 * @vitest-environment jsdom
 */
import React from 'react';
import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, cleanup, fireEvent } from '@testing-library/react';
import { NextIntlClientProvider } from 'next-intl';

import en from '../../../../messages/en.json';
import ru from '../../../../messages/ru.json';
import type { CoachMessage, GameResult } from '@/types/coach';
import MessageCards from '../cards/MessageCards';

const START = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1';
const base: CoachMessage = { id: 'm', role: 'assistant', content: 'x', timestamp: new Date(0) };

function renderCards(message: CoachMessage, handlers: Partial<React.ComponentProps<typeof MessageCards>> = {}, messages: object = en) {
  const h = {
    boardFen: START,
    disabled: false,
    onBoardActions: vi.fn(),
    onShowBoard: vi.fn(),
    onOpenGame: vi.fn(),
    onSend: vi.fn(),
    ...handlers,
  };
  render(
    <NextIntlClientProvider locale="en" messages={messages as Record<string, unknown>}>
      <MessageCards message={message} {...h} />
    </NextIntlClientProvider>,
  );
  return h;
}

afterEach(cleanup);

describe('MessageCards', () => {
  it('renders nothing for a restored message without cards', () => {
    renderCards(base);
    expect(screen.queryByTestId('message-cards')).toBeNull();
    expect(screen.queryByTestId('shown-on-board')).toBeNull();
  });

  it('game list: tap opens the turn’s own card, master games by id, no id is not a button', () => {
    const own: GameResult = {
      id: 'g1', white_name: 'me', black_name: 'you', result: '1-0', date: '2024.01.02', eco: 'C20',
      opening: '', event: '', white_elo: null, black_elo: null, source: 'user', pgn: '1. e4 1-0',
    };
    const h = renderCards({ ...base, gameResults: [own] });
    expect(screen.getByText(en.coach.sourceUser)).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: en.coach.cardOpenGame.replace('{white}', 'me').replace('{black}', 'you') }));
    expect(h.onOpenGame).toHaveBeenCalledWith(own);
    cleanup();

    const h2 = renderCards({
      ...base,
      summaries: [{ kind: 'game_list', games: [{ id: 7, white: 'Kasparov', black: 'Topalov', result: '1-0', year: 1999 }, { white: 'Morphy', black: 'Duke', result: '1-0' }] }],
    });
    const rows = screen.getAllByTestId('card-game');
    expect(rows[0].tagName).toBe('BUTTON');
    expect(rows[1].tagName).toBe('DIV');
    fireEvent.click(rows[0]);
    expect(h2.onOpenGame).toHaveBeenCalledWith(expect.objectContaining({ id: 7, white_name: 'Kasparov', date: '1999' }));
  });

  it('opening card: name, ECO, W/D/L bar; «Learn the line» sends a prompt', () => {
    const h = renderCards({
      ...base,
      summaries: [{ kind: 'opening', name: 'Sicilian Defense', eco: 'B20', moves_san: ['e4', 'c5'], stats: { white: 36, draw: 40, black: 24, games: 1200 } }],
    });
    expect(screen.getByText('Sicilian Defense')).toBeTruthy();
    expect(screen.getByText('B20')).toBeTruthy();
    expect(screen.getByText('1. e4 c5')).toBeTruthy();
    expect(screen.getByTestId('opening-wdl').children).toHaveLength(3);
    fireEvent.click(screen.getByTestId('card-opening-learn'));
    expect(h.onSend).toHaveBeenCalledWith('Teach me the main line of Sicilian Defense');
  });

  it('puzzle card: «Solve» replays the turn’s set_puzzle and shows the board', () => {
    const setPuzzle = { type: 'set_puzzle' as const, fen: START, solution: ['e2e4'], puzzle_id: 'p1' };
    const h = renderCards({
      ...base,
      boardActions: [setPuzzle],
      summaries: [{ kind: 'puzzle', puzzle_id: 'p1', fen: START, rating: 1500, themes: ['fork'] }],
    });
    expect(screen.getByTestId('mini-board').children).toHaveLength(64);
    fireEvent.click(screen.getByTestId('card-puzzle-solve'));
    expect(h.onBoardActions).toHaveBeenCalledWith([setPuzzle]);
    expect(h.onShowBoard).toHaveBeenCalled();
  });

  it('puzzle card without its board action asks the coach for it', () => {
    const h = renderCards({ ...base, summaries: [{ kind: 'puzzle', puzzle_id: 'p9', fen: START }] });
    fireEvent.click(screen.getByTestId('card-puzzle-solve'));
    expect(h.onSend).toHaveBeenCalledWith('Give me puzzle p9 again');
  });

  it('«Shown on the board» chip brings the board into view; static without a handler', () => {
    const h = renderCards({ ...base, boardActions: [{ type: 'flip_board' }] }, {}, ru);
    const chip = screen.getByTestId('shown-on-board');
    expect(chip.textContent).toBe('Показано на доске');
    fireEvent.click(chip);
    expect(h.onShowBoard).toHaveBeenCalled();
    cleanup();
    renderCards({ ...base, boardActions: [{ type: 'flip_board' }] }, { onShowBoard: undefined });
    expect(screen.getByTestId('shown-on-board').tagName).toBe('SPAN');
  });

  it('keeps one card per kind (the latest) and no card for critical moments yet', () => {
    renderCards({
      ...base,
      summaries: [
        { kind: 'engine_line', fen: START, eval_cp: 10, lines: [{ san: ['d4'], eval_cp: 10 }] },
        { kind: 'engine_line', fen: START, eval_cp: 30, lines: [{ san: ['e4'], eval_cp: 30 }] },
        { kind: 'critical_moments', moments: [{ ply: 1, san: 'e4', eval_before: 0, eval_after: 0, label: 'mistake' }] },
      ],
    });
    expect(screen.getAllByTestId('card-engine-line')).toHaveLength(1);
    expect(screen.getByTestId('eval-pill').textContent).toBe('+0.3');
  });
});
