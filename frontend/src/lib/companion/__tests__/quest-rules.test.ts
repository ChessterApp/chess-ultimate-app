/**
 * @vitest-environment node
 *
 * Companion Phase 5 — pure quest state-machine rules. The pilot quest wraps the
 * Watchtower chapter (objective = complete all six nodes). Covers the state
 * transitions and the first-completion commit guard. R2 (quest state never gates
 * an educational path) is asserted in r2-invariant.test.ts.
 */
import { describe, it, expect } from 'vitest';
import {
  WATCHTOWER_QUEST_ID,
  computeQuestState,
  objectivesComplete,
  shouldCommitCompletion,
} from '../quest-rules';

const base = {
  prerequisitesMet: true,
  started: false,
  done: 0,
  total: 6,
  alreadyCompleted: false,
};

describe('objectivesComplete', () => {
  it('is true only when every required node is done', () => {
    expect(objectivesComplete(6, 6)).toBe(true);
    expect(objectivesComplete(7, 6)).toBe(true);
    expect(objectivesComplete(5, 6)).toBe(false);
    expect(objectivesComplete(0, 0)).toBe(false); // nothing to complete
  });
});

describe('computeQuestState', () => {
  it('locked → available → active → objectives_complete → completed', () => {
    expect(computeQuestState({ ...base, prerequisitesMet: false })).toBe('locked');
    expect(computeQuestState({ ...base })).toBe('available');
    expect(computeQuestState({ ...base, started: true, done: 2 })).toBe('active');
    expect(computeQuestState({ ...base, started: true, done: 6 })).toBe('objectives_complete');
    expect(computeQuestState({ ...base, started: true, done: 6, alreadyCompleted: true })).toBe(
      'completed',
    );
  });

  it('completed is terminal regardless of other inputs', () => {
    expect(
      computeQuestState({ ...base, prerequisitesMet: false, done: 0, alreadyCompleted: true }),
    ).toBe('completed');
  });
});

describe('shouldCommitCompletion', () => {
  it('commits only when started, objectives met, and not already completed', () => {
    expect(shouldCommitCompletion({ ...base, started: true, done: 6 })).toBe(true);
  });
  it('does NOT commit before start, before objectives, or after completion', () => {
    expect(shouldCommitCompletion({ ...base, started: false, done: 6 })).toBe(false);
    expect(shouldCommitCompletion({ ...base, started: true, done: 5 })).toBe(false);
    expect(
      shouldCommitCompletion({ ...base, started: true, done: 6, alreadyCompleted: true }),
    ).toBe(false);
  });
});

describe('constants', () => {
  it('names the seeded pilot quest', () => {
    expect(WATCHTOWER_QUEST_ID).toBe('watchtower');
  });
});
