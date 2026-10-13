import { describe, it, expect } from 'vitest';
import { applyTabActions, EMPTY_ANNOTATIONS, routeBoardActions } from '../route-board-actions';
import type { BoardAction } from '@/types/coach';
import type { GameStateView } from '../boards-api';

const arrows = [{ from: 'e2', to: 'e4', brush: 'green' }];

describe('routeBoardActions — by board_id', () => {
  it('arrows and highlights addressed to a game tab go to that tab', () => {
    const r = routeBoardActions(
      [
        { type: 'draw_arrows', arrows, board_id: 'tab1' },
        { type: 'highlight_squares', squares: ['e4'], color: 'red', board_id: 'tab1' },
      ],
      ['tab1', 'tab2'],
    );
    expect(r.study).toEqual([]);
    expect(r.tabs.tab1.map((a) => a.type)).toEqual(['draw_arrows', 'highlight_squares']);
    expect(r.focusTab).toBe('tab1');
  });

  it('actions without a tab id, or for an unknown board, go to the study board', () => {
    const actions: BoardAction[] = [
      { type: 'draw_arrows', arrows },
      { type: 'draw_arrows', arrows, board_id: 'study-1' },
    ];
    const r = routeBoardActions(actions, ['tab1']);
    expect(r.study).toEqual(actions);
    expect(r.tabs).toEqual({});
    expect(r.focusTab).toBeNull();
  });

  it('a position change addressed to a tab is shown on the study board', () => {
    const r = routeBoardActions([{ type: 'set_fen', fen: '8/8/8/8/8/8/8/8 w - - 0 1', board_id: 'tab1' }], ['tab1']);
    expect(r.study).toHaveLength(1);
    expect(r.tabs).toEqual({});
  });

  it('picks out the game state', () => {
    const game = { board_id: 'g' } as GameStateView;
    const r = routeBoardActions([{ type: 'game', game }], []);
    expect(r.game).toBe(game);
    expect(r.study).toEqual([]);
  });
});

describe('applyTabActions', () => {
  const start = { index: 3, annotations: EMPTY_ANNOTATIONS };

  it('navigates within the game', () => {
    expect(applyTabActions(start, [{ type: 'navigate', direction: 'first' }], 9).index).toBe(-1);
    expect(applyTabActions(start, [{ type: 'navigate', direction: 'last' }], 9).index).toBe(9);
    expect(applyTabActions(start, [{ type: 'navigate', direction: 'next' }], 3).index).toBe(3);
    expect(applyTabActions({ ...start, index: -1 }, [{ type: 'navigate', direction: 'prev' }], 9).index).toBe(-1);
  });

  it('stores arrows and highlights after the coach moves there', () => {
    const s = applyTabActions(
      start,
      [
        { type: 'navigate', direction: 'next' },
        { type: 'draw_arrows', arrows },
        { type: 'highlight_squares', squares: ['d5'], color: 'yellow' },
      ],
      9,
    );
    expect(s).toEqual({ index: 4, annotations: { arrows, highlights: ['d5'] } });
  });
});
