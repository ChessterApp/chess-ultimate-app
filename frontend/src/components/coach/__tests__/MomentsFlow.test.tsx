/**
 * @vitest-environment jsdom
 */
import React from 'react';
import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, cleanup, fireEvent } from '@testing-library/react';
import { NextIntlClientProvider } from 'next-intl';

import en from '../../../../messages/en.json';
import ru from '../../../../messages/ru.json';
import type { ReviewMomentsSummary } from '@/lib/coach/tool-summary';
import MomentsFlow, { useMomentsFlow } from '../MomentsFlow';

const coach = en.coach;

const REVIEW: ReviewMomentsSummary = {
  kind: 'review_moments',
  game: { white: 'Student', black: 'Bot', result: '0-1' },
  moments: [
    {
      ply: 25,
      fen: 'r3k3/8/8/1N6/8/8/8/4K3 w - - 0 13',
      played: 'Ke2',
      best: 'Nc7+',
      best_uci: 'b5c7',
      motif: 'fork',
      question: 'The game went 13.Ke2. Find a stronger move for White.',
      explanation: 'Better was 13.Nc7+ — a fork.',
    },
    {
      ply: 62,
      fen: '3rk3/8/8/3Q4/8/8/8/4K3 b - - 0 31',
      played: 'Kf8',
      best: 'Rxd5',
      best_uci: 'd8d5',
      question: 'Find a stronger move for Black.',
      explanation: 'Better was 31...Rxd5.',
    },
  ],
};

/** The flow driven by its real hook; «board» buttons stand in for moves on the board. */
function Harness({ onAsk, onExit, messages = en }: { onAsk: (m: string) => void; onExit: () => void; messages?: object }) {
  const controls = useMomentsFlow(REVIEW);
  return (
    <NextIntlClientProvider locale="en" messages={messages as Record<string, unknown>}>
      <div data-testid="board" data-fen={controls.board?.fen ?? ''} data-orientation={controls.board?.orientation ?? ''}
        data-arrows={JSON.stringify(controls.board?.arrows ?? [])} data-highlights={(controls.board?.highlights ?? []).join(',')} />
      <button type="button" onClick={() => controls.move('b5', 'c7')}>board-best</button>
      <button type="button" onClick={() => controls.move('e1', 'd2')}>board-wrong</button>
      <button type="button" onClick={() => controls.move('d8', 'd5')}>board-best-2</button>
      <MomentsFlow controls={controls} onAsk={onAsk} onExit={onExit} />
    </NextIntlClientProvider>
  );
}

const board = () => screen.getByTestId('board');

afterEach(cleanup);

describe('MomentsFlow', () => {
  it('shows the moment: header, step label, question, its position with the player to move', () => {
    render(<Harness onAsk={vi.fn()} onExit={vi.fn()} />);
    expect(screen.getByText(coach.momentsTitle)).toBeTruthy();
    expect(screen.getByText('Moment 1 of 2')).toBeTruthy();
    expect(screen.getByTestId('step-prompt').textContent).toBe(REVIEW.moments[0].question);
    expect(board().dataset.fen).toBe(REVIEW.moments[0].fen);
    expect(board().dataset.orientation).toBe('white');
  });

  it('«Подсказка» lights the better move’s square; «Спросить» asks about the moment', () => {
    const onAsk = vi.fn();
    render(<Harness onAsk={onAsk} onExit={vi.fn()} />);
    fireEvent.click(screen.getByRole('button', { name: coach.gameHint }));
    expect(board().dataset.highlights).toBe('b5');
    fireEvent.click(screen.getByRole('button', { name: coach.stepAsk }));
    expect(onAsk).toHaveBeenCalledWith('Explain moment 1 (13.Ke2)');
  });

  it('a wrong move: red panel with the student’s move, the better move drawn, a «why not» chip, retry', () => {
    const onAsk = vi.fn();
    render(<Harness onAsk={onAsk} onExit={vi.fn()} />);
    fireEvent.click(screen.getByText('board-wrong'));
    fireEvent.click(screen.getByRole('button', { name: coach.stepCheck }));
    const panel = screen.getByTestId('step-feedback');
    expect(panel.textContent).toContain(`${coach.stepWrong} 13.Kd2`);
    expect(panel.textContent).toContain('Better was 13.Nc7+');
    expect(panel.textContent).toContain(coach.motifFork);
    expect(JSON.parse(board().dataset.arrows!)).toEqual([{ from: 'b5', to: 'c7', brush: 'green' }]);
    expect(board().dataset.fen).toBe(REVIEW.moments[0].fen);
    fireEvent.click(screen.getByRole('button', { name: 'Why not 13.Kd2?' }));
    expect(onAsk).toHaveBeenCalledWith('In moment 1, why is 13.Kd2 worse than 13.Nc7+?');
    fireEvent.click(screen.getByRole('button', { name: coach.stepRetry }));
    expect(screen.queryByTestId('step-feedback')).toBeNull();
  });

  it('a correct move: green panel, no XP while none is credited, then the next moment', () => {
    render(<Harness onAsk={vi.fn()} onExit={vi.fn()} />);
    fireEvent.click(screen.getByText('board-best'));
    fireEvent.click(screen.getByRole('button', { name: coach.stepCheck }));
    expect(screen.getByTestId('step-feedback').textContent).toContain(`${coach.stepCorrect} 13.Nc7+`);
    expect(screen.getByRole('button', { name: 'Why not 13.Ke2?' })).toBeTruthy();
    expect(screen.queryByTestId('step-xp')).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: coach.stepNext }));
    expect(screen.getByText('Moment 2 of 2')).toBeTruthy();
    expect(board().dataset.orientation).toBe('black');
  });

  it('after the last moment: the first-try count, back to the chat, or again', () => {
    const onExit = vi.fn();
    render(<Harness onAsk={vi.fn()} onExit={onExit} />);
    fireEvent.click(screen.getByText('board-wrong'));
    fireEvent.click(screen.getByRole('button', { name: coach.stepCheck }));
    fireEvent.click(screen.getByRole('button', { name: coach.stepRetry }));
    fireEvent.click(screen.getByText('board-best'));
    fireEvent.click(screen.getByRole('button', { name: coach.stepCheck }));
    fireEvent.click(screen.getByRole('button', { name: coach.stepNext }));
    fireEvent.click(screen.getByText('board-best-2'));
    fireEvent.click(screen.getByRole('button', { name: coach.stepCheck }));
    fireEvent.click(screen.getByRole('button', { name: coach.stepNext }));
    expect(screen.getByTestId('moments-done-score').textContent).toBe('Found on the first try: 1 of 2');
    expect(board().dataset.fen).toBe('');
    fireEvent.click(screen.getByRole('button', { name: coach.momentsDoneBack }));
    expect(onExit).toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: coach.momentsDoneAgain }));
    expect(screen.getByText('Moment 1 of 2')).toBeTruthy();
  });

  it('✕ leaves the review', () => {
    const onExit = vi.fn();
    render(<Harness onAsk={vi.fn()} onExit={onExit} />);
    fireEvent.click(screen.getByRole('button', { name: coach.momentsExit }));
    expect(onExit).toHaveBeenCalled();
  });

  it('renders in Russian', () => {
    render(<Harness onAsk={vi.fn()} onExit={vi.fn()} messages={ru} />);
    expect(screen.getByText('Момент 1 из 2')).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Спросить' })).toBeTruthy();
  });
});
