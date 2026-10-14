import { describe, it, expect } from 'vitest';
import {
  currentMoment,
  initialMomentsFlow,
  isBestMove,
  momentsBoard,
  momentsFlow,
  numberedMove,
  type MomentsFlowEvent,
  type MomentsFlowState,
} from '../moments-flow';
import type { ReviewMoment } from '../tool-summary';

// 13.Nc7+ forks king and rook; the game went 13.Ke2.
const FORK: ReviewMoment = {
  ply: 25,
  fen: 'r3k3/8/8/1N6/8/8/8/4K3 w - - 0 13',
  played: 'Ke2',
  best: 'Nc7+',
  best_uci: 'b5c7',
  motif: 'fork',
  question: 'Найдите ход сильнее.',
  explanation: 'Сильнее 13.Nc7+ — вилка.',
};
// Black to move: 31...Rxd5 wins the queen.
const HANGING: ReviewMoment = {
  ply: 62,
  fen: '3rk3/8/8/3Q4/8/8/8/4K3 b - - 0 31',
  played: 'Kf8',
  best: 'Rxd5',
  best_uci: 'd8d5',
  question: 'Найдите ход сильнее за чёрных.',
  explanation: 'Сильнее 31...Rxd5.',
};
// White promotes: 1.a8=Q is best.
const PROMO: ReviewMoment = {
  ply: 1,
  fen: '7k/P7/8/8/8/8/8/K7 w - - 0 1',
  played: 'Kb2',
  best: 'a8=Q+',
  best_uci: 'a7a8q',
  question: '?',
  explanation: '!',
};

const run = (events: MomentsFlowEvent[], from: MomentsFlowState = initialMomentsFlow([FORK, HANGING])) =>
  events.reduce(momentsFlow, from);
const play = (from: string, to: string, promotion?: string): MomentsFlowEvent => ({ type: 'move', from, to, promotion });

describe('momentsFlow', () => {
  it('starts on the first moment, its position with the player to move', () => {
    const s = initialMomentsFlow([FORK, HANGING]);
    expect(currentMoment(s)).toBe(FORK);
    expect(s.step).toEqual({ phase: 'idle', index: 0, total: 2, attempts: 0 });
    expect(momentsBoard(s)).toEqual({ fen: FORK.fen, arrows: [], highlights: [], movable: true, orientation: 'white' });
  });

  it('holds a move until «Проверить»; the board shows it and takes no other', () => {
    const s = run([play('b5', 'c7')]);
    expect(s.step.phase).toBe('moved');
    expect(s.pending?.san).toBe('Nc7+');
    expect(momentsBoard(s)?.fen).toBe(s.pending?.fen);
    expect(momentsBoard(s)?.movable).toBe(false);
    expect(run([play('e1', 'd2')], s)).toBe(s);
    const undone = run([{ type: 'undo' }], s);
    expect(undone.step.phase).toBe('idle');
    expect(momentsBoard(undone)?.fen).toBe(FORK.fen);
  });

  it('ignores illegal moves', () => {
    const s = initialMomentsFlow([FORK]);
    expect(momentsFlow(s, play('b5', 'b7'))).toBe(s);
    expect(momentsFlow(s, { type: 'check' })).toBe(s);
  });

  it('a correct move: green, kept on the board, first-try counted, then the next moment', () => {
    const s = run([play('b5', 'c7'), { type: 'check' }]);
    expect(s.step.phase).toBe('correct');
    expect(s.checked).toMatchObject({ correct: true, move: { san: 'Nc7+' } });
    expect(s.firstTry).toBe(1);
    expect(momentsBoard(s)).toMatchObject({ fen: s.pending?.fen, arrows: [], movable: false });
    const next = momentsFlow(s, { type: 'next' });
    expect(currentMoment(next)).toBe(HANGING);
    expect(next).toMatchObject({ pending: null, checked: null, hint: false });
    expect(momentsBoard(next)).toMatchObject({ fen: HANGING.fen, orientation: 'black', movable: true });
  });

  it('a wrong move: red, taken back, the better move drawn; retry, then no first-try credit', () => {
    const s = run([play('e1', 'd2'), { type: 'check' }]);
    expect(s.step.phase).toBe('wrong');
    expect(s.checked).toMatchObject({ correct: false, move: { san: 'Kd2' } });
    expect(momentsBoard(s)).toEqual({
      fen: FORK.fen,
      arrows: [{ from: 'b5', to: 'c7', brush: 'green' }],
      highlights: [],
      movable: false,
      orientation: 'white',
    });
    expect(momentsFlow(s, { type: 'next' })).toBe(s); // a wrong answer is not skipped
    const again = run([{ type: 'retry' }, play('b5', 'c7'), { type: 'check' }], s);
    expect(again.step).toMatchObject({ phase: 'correct', attempts: 2 });
    expect(again.firstTry).toBe(0);
  });

  it('«Подсказка» lights the better move’s square, and a hinted answer is not first-try', () => {
    const s = run([{ type: 'hint' }]);
    expect(momentsBoard(s)?.highlights).toEqual(['b5']);
    const solved = run([play('b5', 'c7'), { type: 'check' }], s);
    expect(momentsBoard(solved)?.highlights).toEqual([]);
    expect(solved.firstTry).toBe(0);
  });

  it('the last «Дальше» ends the review', () => {
    const s = run([
      play('b5', 'c7'), { type: 'check' }, { type: 'next' },
      play('d8', 'd5'), { type: 'check' }, { type: 'next' },
    ]);
    expect(s.step.phase).toBe('done');
    expect(s.firstTry).toBe(2);
    expect(currentMoment(s)).toBeNull();
    expect(momentsBoard(s)).toBeNull();
    expect(momentsFlow(s, play('b5', 'c7'))).toBe(s);
  });

  it('promotions: the default queen matches a8=Q, an underpromotion does not', () => {
    const queen = run([play('a7', 'a8'), { type: 'check' }], initialMomentsFlow([PROMO]));
    expect(queen.step.phase).toBe('correct');
    const knight = run([play('a7', 'a8', 'n'), { type: 'check' }], initialMomentsFlow([PROMO]));
    expect(knight.step.phase).toBe('wrong');
  });

  it('restart and an empty review', () => {
    const s = run([play('b5', 'c7'), { type: 'restart', moments: [HANGING] }]);
    expect(s).toEqual(initialMomentsFlow([HANGING]));
    expect(initialMomentsFlow([]).step.phase).toBe('done');
    expect(momentsBoard(initialMomentsFlow([]))).toBeNull();
  });
});

describe('helpers', () => {
  it('isBestMove compares squares and promotion', () => {
    expect(isBestMove({ from: 'b5', to: 'c7' }, 'b5c7')).toBe(true);
    expect(isBestMove({ from: 'b5', to: 'd6' }, 'b5c7')).toBe(false);
    expect(isBestMove({ from: 'a7', to: 'a8', promotion: 'q' }, 'a7a8q')).toBe(true);
    expect(isBestMove({ from: 'a7', to: 'a8', promotion: 'r' }, 'a7a8q')).toBe(false);
  });

  it('numberedMove numbers from the ply', () => {
    expect(numberedMove(FORK, 'Nc7+')).toBe('13.Nc7+');
    expect(numberedMove(HANGING, 'Rxd5')).toBe('31...Rxd5');
  });
});
