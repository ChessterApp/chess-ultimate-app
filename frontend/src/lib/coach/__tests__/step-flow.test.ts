import { describe, it, expect } from 'vitest';
import { canCheck, initialStepFlow, stepFlow, stepXp, type StepFlowEvent, type StepFlowState } from '../step-flow';

const run = (events: StepFlowEvent[], from: StepFlowState) => events.reduce(stepFlow, from);

describe('StepFlow state machine', () => {
  it('idle → moved → checking → correct → next step', () => {
    let s = initialStepFlow(3);
    expect(s).toEqual({ phase: 'idle', index: 0, total: 3, attempts: 0 });
    expect(canCheck(s)).toBe(false);
    s = stepFlow(s, { type: 'move' });
    expect(s.phase).toBe('moved');
    expect(canCheck(s)).toBe(true);
    s = stepFlow(s, { type: 'check' });
    expect(s.phase).toBe('checking');
    expect(canCheck(s)).toBe(false);
    s = stepFlow(s, { type: 'result', correct: true });
    expect(s).toMatchObject({ phase: 'correct', attempts: 1 });
    s = stepFlow(s, { type: 'next' });
    expect(s).toEqual({ phase: 'idle', index: 1, total: 3, attempts: 0 });
  });

  it('a wrong answer counts an attempt and retry goes back to idle on the same step', () => {
    const s = run([{ type: 'move' }, { type: 'check' }, { type: 'result', correct: false }], initialStepFlow(2));
    expect(s).toMatchObject({ phase: 'wrong', attempts: 1, index: 0 });
    const again = run([{ type: 'retry' }, { type: 'move' }, { type: 'check' }, { type: 'result', correct: true }], s);
    expect(again).toMatchObject({ phase: 'correct', attempts: 2, index: 0 });
  });

  it('next after the last step is done', () => {
    const s = run([{ type: 'move' }, { type: 'check' }, { type: 'result', correct: true }, { type: 'next' }], initialStepFlow(1));
    expect(s.phase).toBe('done');
  });

  it('a move can be undone before checking', () => {
    expect(run([{ type: 'move' }, { type: 'undo' }], initialStepFlow(1)).phase).toBe('idle');
  });

  it('ignores events out of order', () => {
    const idle = initialStepFlow(2);
    expect(stepFlow(idle, { type: 'check' })).toBe(idle);
    expect(stepFlow(idle, { type: 'next' })).toBe(idle);
    expect(stepFlow(idle, { type: 'result', correct: true })).toBe(idle);
    const wrong = run([{ type: 'move' }, { type: 'check' }, { type: 'result', correct: false }], idle);
    expect(stepFlow(wrong, { type: 'next' })).toBe(wrong);
    expect(stepFlow(wrong, { type: 'move' })).toBe(wrong);
  });

  it('restart resets to a new length; zero steps is done', () => {
    const s = run([{ type: 'move' }, { type: 'restart', total: 4 }], initialStepFlow(1));
    expect(s).toEqual({ phase: 'idle', index: 0, total: 4, attempts: 0 });
    expect(initialStepFlow(0).phase).toBe('done');
  });

  it('xp: full first try, half on the second, none after', () => {
    expect(stepXp(1)).toBe(10);
    expect(stepXp(2)).toBe(5);
    expect(stepXp(3)).toBe(0);
  });
});
