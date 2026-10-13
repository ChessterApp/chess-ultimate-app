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
  | { type: 'restart'; total: number };

export function initialStepFlow(total: number): StepFlowState {
  return { phase: total > 0 ? 'idle' : 'done', index: 0, total, attempts: 0 };
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
      return initialStepFlow(event.total);
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
