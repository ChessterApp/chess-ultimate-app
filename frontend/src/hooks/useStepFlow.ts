import { useCallback, useReducer, useRef } from 'react';
import { initialStepFlow, stepFlow, stepXp, type StepFlowState } from '@/lib/coach/step-flow';

export interface StepComplete {
  correct: boolean;
  /** Checks made on the step so far, this one included. */
  attempts: number;
  /** XP the step earned (0 when wrong). */
  xp: number;
}

export interface StepFlowControls {
  state: StepFlowState;
  move: () => void;
  undo: () => void;
  /** Check the answer with `verify`; reports the outcome through onStepComplete. */
  check: (verify: () => boolean | Promise<boolean>) => Promise<boolean>;
  retry: () => void;
  next: () => void;
  restart: (total: number) => void;
}

/** The StepFlow state machine as a hook, with the XP hook on every checked answer. */
export function useStepFlow(total: number, onStepComplete?: (result: StepComplete) => void): StepFlowControls {
  const [state, dispatch] = useReducer(stepFlow, total, initialStepFlow);
  const stateRef = useRef(state);
  stateRef.current = state;
  const completeRef = useRef(onStepComplete);
  completeRef.current = onStepComplete;

  const check = useCallback(async (verify: () => boolean | Promise<boolean>) => {
    if (stateRef.current.phase !== 'moved') return false;
    dispatch({ type: 'check' });
    let correct = false;
    try {
      correct = await verify();
    } finally {
      dispatch({ type: 'result', correct });
    }
    const attempts = stateRef.current.attempts + 1;
    completeRef.current?.({ correct, attempts, xp: correct ? stepXp(attempts) : 0 });
    return correct;
  }, []);

  return {
    state,
    move: useCallback(() => dispatch({ type: 'move' }), []),
    undo: useCallback(() => dispatch({ type: 'undo' }), []),
    check,
    retry: useCallback(() => dispatch({ type: 'retry' }), []),
    next: useCallback(() => dispatch({ type: 'next' }), []),
    restart: useCallback((n: number) => dispatch({ type: 'restart', total: n }), []),
  };
}
