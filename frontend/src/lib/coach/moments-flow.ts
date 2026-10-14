/**
 * «Моменты»: a game review replayed as guided steps (coach redesign P3b).
 * Each moment of a `review_moments` summary is a StepFlow step: the board
 * shows the position before the mistake with the player to move, the student
 * plays a move, «Проверить» compares it with the engine's better move
 * (`best_uci`), and the feedback panel follows.
 *
 * Pure: the step phases are step-flow.ts's; this adds the moments, the move
 * held until it is checked, the hint and what the board shows.
 */

import { Chess } from 'chess.js';
import type { ReviewMoment } from './tool-summary';
import { initialStepFlow, stepFlow, type StepFlowState } from './step-flow';

export interface MomentMove {
  from: string;
  to: string;
  promotion?: string;
  san: string;
  /** The position after the move. */
  fen: string;
}

export interface MomentsFlowState {
  moments: ReviewMoment[];
  /** `step.index` is the current moment. */
  step: StepFlowState;
  /** The move on the board, not checked yet. */
  pending: MomentMove | null;
  /** The move last checked on this moment, and whether it was the better move. */
  checked: { move: MomentMove; correct: boolean } | null;
  /** «Подсказка» was used on this moment: the better move's square is lit. */
  hint: boolean;
  /** Moments found on the first try. */
  firstTry: number;
}

export type MomentsFlowEvent =
  | { type: 'move'; from: string; to: string; promotion?: string }
  | { type: 'undo' }
  | { type: 'check' }
  | { type: 'retry' }
  | { type: 'next' }
  | { type: 'hint' }
  | { type: 'restart'; moments: ReviewMoment[] };

export function initialMomentsFlow(moments: ReviewMoment[] = []): MomentsFlowState {
  return { moments, step: initialStepFlow(moments.length), pending: null, checked: null, hint: false, firstTry: 0 };
}

export function currentMoment(state: MomentsFlowState): ReviewMoment | null {
  return state.moments[state.step.index] ?? null;
}

const squares = (uci: string) => ({ from: uci.slice(0, 2), to: uci.slice(2, 4), promotion: uci[4] || undefined });

/** The student's move is the better move (a promotion must pick the same piece; queen by default). */
export function isBestMove(move: Pick<MomentMove, 'from' | 'to' | 'promotion'>, bestUci: string): boolean {
  const best = squares(bestUci);
  if (move.from !== best.from || move.to !== best.to) return false;
  return !best.promotion || (move.promotion ?? 'q') === best.promotion;
}

function play(fen: string, from: string, to: string, promotion?: string): MomentMove | null {
  try {
    const chess = new Chess(fen);
    const isPawn = chess.get(from as Parameters<Chess['get']>[0])?.type === 'p';
    const promo = isPawn && (to[1] === '8' || to[1] === '1') ? (promotion ?? 'q') : undefined;
    const m = chess.move({ from, to, promotion: promo });
    return { from, to, promotion: promo, san: m.san, fen: chess.fen() };
  } catch {
    return null; // illegal: the board snaps back
  }
}

export function momentsFlow(state: MomentsFlowState, event: MomentsFlowEvent): MomentsFlowState {
  const moment = currentMoment(state);
  const { phase } = state.step;
  switch (event.type) {
    case 'move': {
      // One move at a time: «Отменить ход» takes it back before another (as in PuzzleFlow).
      if (!moment || phase !== 'idle') return state;
      const move = play(moment.fen, event.from, event.to, event.promotion);
      if (!move) return state;
      return { ...state, pending: move, step: stepFlow(state.step, { type: 'move' }) };
    }
    case 'undo':
      return phase === 'moved' ? { ...state, pending: null, step: stepFlow(state.step, { type: 'undo' }) } : state;
    case 'check': {
      if (!moment || !state.pending || phase !== 'moved') return state;
      const correct = isBestMove(state.pending, moment.best_uci);
      const step = stepFlow(stepFlow(state.step, { type: 'check' }), { type: 'result', correct });
      return {
        ...state,
        step,
        // A correct move stays on the board; a wrong one is taken back and the better move drawn.
        pending: correct ? state.pending : null,
        checked: { move: state.pending, correct },
        firstTry: state.firstTry + (correct && step.attempts === 1 && !state.hint ? 1 : 0),
      };
    }
    case 'retry':
      return phase === 'wrong' ? { ...state, checked: null, step: stepFlow(state.step, { type: 'retry' }) } : state;
    case 'next': {
      if (phase !== 'correct') return state;
      return { ...state, step: stepFlow(state.step, { type: 'next' }), pending: null, checked: null, hint: false };
    }
    case 'hint':
      return moment && (phase === 'idle' || phase === 'moved') ? { ...state, hint: true } : state;
    case 'restart':
      return initialMomentsFlow(event.moments);
  }
}

export interface MomentsBoard {
  fen: string;
  /** The better move as a green arrow after a wrong answer. */
  arrows: Array<{ from: string; to: string; brush: string }>;
  /** The better move's square after «Подсказка». */
  highlights: string[];
  /** Moves are taken only while no move waits for «Проверить». */
  movable: boolean;
  /** The side to move in the moment — the board is seen from there. */
  orientation: 'white' | 'black';
}

/** What the board shows for the current moment (null once the review is over). */
export function momentsBoard(state: MomentsFlowState): MomentsBoard | null {
  const moment = currentMoment(state);
  if (!moment || state.step.phase === 'done') return null;
  const best = squares(moment.best_uci);
  const { phase } = state.step;
  return {
    fen: state.pending?.fen ?? moment.fen,
    arrows: phase === 'wrong' ? [{ from: best.from, to: best.to, brush: 'green' }] : [],
    highlights: state.hint && (phase === 'idle' || phase === 'moved') ? [best.from] : [],
    movable: phase === 'idle',
    orientation: moment.fen.split(' ')[1] === 'b' ? 'black' : 'white',
  };
}

/** «13.Nc7+», «21...Qxb2»: a move of the moment, numbered. */
export function numberedMove(moment: Pick<ReviewMoment, 'ply'>, san: string): string {
  const number = Math.ceil(moment.ply / 2);
  return `${number}${moment.ply % 2 === 1 ? '.' : '...'}${san}`;
}
