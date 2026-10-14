/**
 * @vitest-environment jsdom
 */
import React from 'react';
import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, cleanup, fireEvent, within, waitFor } from '@testing-library/react';
import { NextIntlClientProvider } from 'next-intl';

import en from '../../../../messages/en.json';
import PlayStrip, { PlayCoachRow } from '../PlayStrip';
import PlaySetupSheet from '../PlaySetupSheet';
import ResultCard from '../ResultCard';
import type { GameStateView } from '@/lib/coach/boards-api';

vi.mock('next/image', () => ({
  // eslint-disable-next-line @next/next/no-img-element, jsx-a11y/alt-text
  default: (props: React.ImgHTMLAttributes<HTMLImageElement> & { unoptimized?: boolean }) => <img {...props} unoptimized={undefined} />,
}));

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

function handlers() {
  return {
    onHint: vi.fn(),
    onTakeback: vi.fn(),
    onResign: vi.fn(),
    onToggleChat: vi.fn(),
    onReview: vi.fn(),
    onRematch: vi.fn(),
    onClose: vi.fn(),
  };
}

function strip(game: GameStateView, h = handlers(), extra: Partial<{ thinking: boolean; comment: string | null; chatOpen: boolean }> = {}) {
  wrap(
    <PlayStrip game={game} thinking={false} comment={null} chatOpen={false} width={320} {...h} {...extra}>
      <div data-testid="board" />
    </PlayStrip>,
  );
  return h;
}

afterEach(cleanup);

describe('PlayStrip', () => {
  it('coach row with Elo + level and the speech bubble, the board, the student row', () => {
    strip(view({ ply: 2, in_check: true }), handlers(), { comment: 'Too early for Ng5.' });
    expect(screen.getByText(`1200 · ${coach.levelAmateur}`)).toBeTruthy();
    expect(screen.getByTestId('coach-bubble').textContent).toBe('Too early for Ng5.');
    expect(screen.getByTestId('board')).toBeTruthy();
    expect(screen.getByTestId('play-status').textContent).toBe(`· ${coach.gameYourMove} · ${coach.gameCheck}`);
    // After 1.e4 e5 it is move 2.
    expect(screen.getByTestId('play-move-number').textContent).toBe('Move 2');
  });

  it('the action bar is wired to hint / take back / chat', () => {
    const h = strip(view({ ply: 2 }));
    const bar = within(screen.getByRole('toolbar'));
    fireEvent.click(bar.getByText(coach.gameHint));
    fireEvent.click(bar.getByText(coach.playTakebackShort));
    fireEvent.click(bar.getByText(coach.playChat));
    expect(h.onHint).toHaveBeenCalledTimes(1);
    expect(h.onTakeback).toHaveBeenCalledTimes(1);
    expect(h.onToggleChat).toHaveBeenCalledTimes(1);
  });

  it('nothing to take back on move 0; buttons off while the coach thinks', () => {
    strip(view({ ply: 0 }));
    expect((screen.getByText(coach.playTakebackShort).closest('button') as HTMLButtonElement).disabled).toBe(true);
    cleanup();
    strip(view({ ply: 3, student_to_move: false }), handlers(), { thinking: true });
    expect(screen.getByTestId('play-status').textContent).toContain(coach.gameCoachThinking);
    expect((screen.getByText(coach.gameHint).closest('button') as HTMLButtonElement).disabled).toBe(true);
    // Chat stays available.
    expect((screen.getByText(coach.playChat).closest('button') as HTMLButtonElement).disabled).toBe(false);
  });

  it('resign asks in the styled dialog first — Esc keeps playing, confirm resigns', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm');
    const h = strip(view());
    const bar = within(screen.getByRole('toolbar'));
    fireEvent.click(bar.getByText(coach.gameResign));
    const dialog = screen.getByRole('dialog');
    expect(dialog.textContent).toContain(coach.gameResignConfirm);
    fireEvent.keyDown(dialog, { key: 'Escape' });
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect(h.onResign).not.toHaveBeenCalled();

    fireEvent.click(bar.getByText(coach.gameResign));
    fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: coach.gameResign }));
    expect(h.onResign).toHaveBeenCalledTimes(1);
    expect(confirmSpy).not.toHaveBeenCalled();
  });

  it('the Chat button shows whether the composer is open', () => {
    strip(view(), handlers(), { chatOpen: true });
    expect(screen.getByText(coach.playChat).closest('button')?.getAttribute('aria-pressed')).toBe('true');
  });

  it('a finished game swaps the action bar for the result card', () => {
    const h = strip(view({ status: 'finished', result: '0-1', termination: 'checkmate', winner: 'engine', ply: 8 }));
    expect(screen.queryByRole('toolbar')).toBeNull();
    fireEvent.click(screen.getByText(coach.resultRematch));
    expect(h.onRematch).toHaveBeenCalled();
  });
});

describe('PlayCoachRow in the mobile shell', () => {
  const long = 'You develop the knight and hold the centre — the right plan. '.repeat(5).trim();

  /** jsdom lays nothing out: give the bubble a box that is shorter than its text. */
  function overflowing(scrollHeight: number) {
    vi.spyOn(HTMLElement.prototype, 'scrollHeight', 'get').mockReturnValue(scrollHeight);
    vi.spyOn(HTMLElement.prototype, 'clientHeight', 'get').mockReturnValue(40);
  }
  afterEach(() => vi.restoreAllMocks());

  it('keeps the whole remark — no line cap, it scrolls', () => {
    wrap(<PlayCoachRow game={view()} thinking={false} comment={long} onExpand={() => {}} />);
    const bubble = screen.getByTestId('coach-bubble');
    expect(bubble.textContent).toBe(long);
    expect(bubble.className).not.toContain('line-clamp');
    expect(bubble.className).toContain('overflow-y-auto');
  });

  it('a remark that overflows fades out with «more»; tapping opens the thread', () => {
    overflowing(200);
    const onExpand = vi.fn();
    wrap(<PlayCoachRow game={view()} thinking={false} comment={long} onExpand={onExpand} />);
    const bubble = screen.getByTestId('coach-bubble');
    expect(bubble.dataset.overflow).toBe('true');
    fireEvent.click(screen.getByTestId('coach-bubble-more'));
    fireEvent.click(bubble);
    expect(onExpand).toHaveBeenCalledTimes(2);
  });

  it('scrolled to its end, the fade and «more» go away', () => {
    overflowing(200);
    wrap(<PlayCoachRow game={view()} thinking={false} comment={long} onExpand={() => {}} />);
    const bubble = screen.getByTestId('coach-bubble');
    bubble.scrollTop = 160;
    fireEvent.scroll(bubble);
    expect(bubble.dataset.overflow).toBeUndefined();
    expect(screen.queryByTestId('coach-bubble-more')).toBeNull();
  });

  it('a short remark: no fade, no «more»', () => {
    overflowing(40);
    wrap(<PlayCoachRow game={view()} thinking={false} comment="Good move." onExpand={() => {}} />);
    expect(screen.getByTestId('coach-bubble').dataset.overflow).toBeUndefined();
    expect(screen.queryByTestId('coach-bubble-more')).toBeNull();
  });

  it('on desktop the bubble keeps ~5 lines and has no «more»', () => {
    overflowing(200);
    wrap(<PlayCoachRow game={view()} thinking={false} comment={long} />);
    expect(screen.getByTestId('coach-bubble').className).toContain('max-h-[6.75rem]');
    expect(screen.queryByTestId('coach-bubble-more')).toBeNull();
  });
});

describe('ResultCard', () => {
  it('shows result and reason; review / rematch / close are wired', () => {
    const h = handlers();
    wrap(
      <ResultCard
        game={view({ status: 'finished', result: '1-0', termination: 'resign', winner: 'student' })}
        onReview={h.onReview}
        onRematch={h.onRematch}
        onClose={h.onClose}
      />,
    );
    expect(screen.getByRole('heading').textContent).toBe(coach.gameWon);
    expect(screen.getByText(`${coach.termResign} · 1-0`)).toBeTruthy();
    fireEvent.click(screen.getByText(coach.resultReview));
    fireEvent.click(screen.getByText(coach.resultRematch));
    fireEvent.click(screen.getByText(coach.gameClose));
    expect(h.onReview).toHaveBeenCalledTimes(1);
    expect(h.onRematch).toHaveBeenCalledTimes(1);
    expect(h.onClose).toHaveBeenCalledTimes(1);
  });

  it('a draw by stalemate', () => {
    const h = handlers();
    wrap(
      <ResultCard
        game={view({ status: 'finished', result: '1/2-1/2', termination: 'stalemate', winner: null })}
        onReview={h.onReview}
        onRematch={h.onRematch}
        onClose={h.onClose}
      />,
    );
    expect(screen.getByRole('heading').textContent).toBe(coach.gameDraw);
    expect(screen.getByText(`${coach.termStalemate} · 1/2-1/2`)).toBeTruthy();
  });
});

describe('PlaySetupSheet', () => {
  it('starts with the chosen colour, strength (snapped, named) and comment mode', () => {
    const onStart = vi.fn();
    wrap(<PlaySetupSheet defaultElo={1234} onStart={onStart} onCancel={vi.fn()} />);
    const slider = screen.getByTestId('game-elo') as HTMLInputElement;
    expect(slider.getAttribute('aria-valuetext')).toBe(`1200 · ${coach.levelAmateur}`);
    fireEvent.click(screen.getByRole('radio', { name: coach.colorBlack }));
    fireEvent.change(slider, { target: { value: '5' } }); // 1800
    expect(screen.getByTestId('game-elo-level').textContent).toBe(coach.levelExpert);
    fireEvent.click(screen.getByRole('radio', { name: coach.commentsEveryShort }));
    expect(screen.getByText(coach.commentsEvery)).toBeTruthy();
    fireEvent.click(screen.getByText(coach.startGame));
    expect(onStart).toHaveBeenCalledWith({ color: 'black', elo: 1800, comment_mode: 'every' });
  });

  it('opens on the last game’s settings', () => {
    const onStart = vi.fn();
    wrap(<PlaySetupSheet initial={{ color: 'random', elo: 2500, comment_mode: 'quiet' }} onStart={onStart} onCancel={vi.fn()} />);
    expect(screen.getByRole('radio', { name: coach.colorRandom }).getAttribute('aria-checked')).toBe('true');
    expect(screen.getByTestId('game-elo-level').textContent).toBe(coach.levelMaster);
    fireEvent.click(screen.getByText(coach.startGame));
    expect(onStart).toHaveBeenCalledWith({ color: 'random', elo: 2500, comment_mode: 'quiet' });
  });

  it('arrow keys move through a segmented control', () => {
    wrap(<PlaySetupSheet onStart={vi.fn()} onCancel={vi.fn()} />);
    fireEvent.keyDown(screen.getByRole('radio', { name: coach.colorWhite }), { key: 'ArrowRight' });
    expect(screen.getByRole('radio', { name: coach.colorBlack }).getAttribute('aria-checked')).toBe('true');
  });

  it('cancels with the close button and with Esc; shows a start error', () => {
    const onCancel = vi.fn();
    wrap(<PlaySetupSheet onStart={vi.fn()} onCancel={onCancel} error="Could not start the game: busy" />);
    expect(screen.getByRole('alert').textContent).toContain('busy');
    fireEvent.click(screen.getByRole('button', { name: coach.cancel }));
    fireEvent.keyDown(window, { key: 'Escape' });
    expect(onCancel).toHaveBeenCalledTimes(2);
  });
});
