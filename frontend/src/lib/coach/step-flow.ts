/**
 * The guided-step state machine behind StepFlow (puzzles now, game-review
 * moments later): idle → moved → checking → correct | wrong → next.
 */

export type StepPhase = 'idle' | 'moved' | 'checking' | 'correct' | 'wrong' | 'done';

export interface StepFlowState {
  phase: StepPhase;
  /** 0-based index of the current step. */
  index: number;
  total: number;
  /** Checks made on the current step (a wrong one counts). */
  attempts: number;
}

export type StepFlowEvent =
  | { type: 'move' }
  | { type: 'undo' }
  | { type: 'check' }
  | { type: 'result'; correct: boolean }
  | { type: 'retry' }
  | { type: 'next' }
  | { type: 'restart'; total: number; start?: number };

/** *start*: the steps already done (a puzzle restored part-way, 19.11) — the last one done shows as just solved. */
export function initialStepFlow(total: number, start = 0): StepFlowState {
  if (total <= 0) return { phase: 'done', index: 0, total, attempts: 0 };
  if (start >= total) return { phase: 'correct', index: total - 1, total, attempts: 1 };
  return { phase: 'idle', index: Math.max(0, start), total, attempts: 0 };
}

export function stepFlow(state: StepFlowState, event: StepFlowEvent): StepFlowState {
  const { phase } = state;
  switch (event.type) {
    case 'move':
      return phase === 'idle' || phase === 'moved' ? { ...state, phase: 'moved' } : state;
    case 'undo':
      return phase === 'moved' ? { ...state, phase: 'idle' } : state;
    case 'check':
      return phase === 'moved' ? { ...state, phase: 'checking' } : state;
    case 'result':
      if (phase !== 'checking') return state;
      return { ...state, phase: event.correct ? 'correct' : 'wrong', attempts: state.attempts + 1 };
    case 'retry':
      return phase === 'wrong' ? { ...state, phase: 'idle' } : state;
    case 'next': {
      if (phase !== 'correct') return state;
      const index = state.index + 1;
      return index >= state.total
        ? { ...state, phase: 'done', index: state.total }
        : { ...state, phase: 'idle', index, attempts: 0 };
    }
    case 'restart':
      return initialStepFlow(event.total, event.start);
  }
}

/** Whether «Проверить» is live. */
export function canCheck(state: StepFlowState): boolean {
  return state.phase === 'moved';
}

/** XP for a correct step: full on the first try, half after a miss, nothing once it took 3+. */
export function stepXp(attempts: number, base = 10): number {
  if (attempts <= 1) return base;
  if (attempts === 2) return Math.round(base / 2);
  return 0;
}

/**
 * What a puzzle's card says over its buttons: the task on the first step, «Верно — теперь следующий ход» on a later
 * one, and that the puzzle is solved once its last step is — the card kept promising a next move over «Отлично! …
 * Дальше» with no move left (tester 25.11).
 */
export function puzzlePrompt(
  state: Pick<StepFlowState, 'phase' | 'index' | 'total'>,
  whiteToMove: boolean,
): 'puzzleSolved' | 'puzzleWhiteToWin' | 'puzzleBlackToWin' | 'puzzleKeepGoing' {
  if (state.phase === 'correct' && state.index + 1 >= state.total) return 'puzzleSolved';
  if (state.index === 0) return whiteToMove ? 'puzzleWhiteToWin' : 'puzzleBlackToWin';
  return 'puzzleKeepGoing';
}
