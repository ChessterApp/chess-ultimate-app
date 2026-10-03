import { describe, it, expect } from 'vitest';
import {
  type TaskDefinition,
  DEFAULT_REWARD_POLICY,
  deriveSubmissionKey,
  judgeSubmission,
  normalizeRewardPolicy,
  pickAssessmentTask,
  rewardForCompetencyPass,
  stableStringify,
  toPublicTask,
} from '../assessment';

function task(over: Partial<TaskDefinition> = {}): TaskDefinition {
  return {
    id: 't1',
    competency_code: 'H_ROOK',
    family: 'H_ROOK_T1',
    fen: '4k3/8/8/8/8/8/8/R3K3 w - - 0 1',
    prompt_en: 'Move the rook.',
    prompt_ru: 'Ход ладьёй.',
    prompt_kk: 'Турамен жүру.',
    solution: { moves: ['a1a8'] },
    validator: 'move',
    hints: [{ en: 'h', ru: 'п', kk: 'к' }],
    ...over,
  };
}

describe('toPublicTask — no-solution invariant (plan A7)', () => {
  it('never exposes the solution or raw hint content', () => {
    const payload = toPublicTask('asg-1', 'H_ROOK', task());
    const serialized = JSON.stringify(payload);
    expect(serialized).not.toContain('a1a8'); // the answer
    expect(serialized).not.toContain('solution');
    expect('solution' in (payload as Record<string, unknown>)).toBe(false);
    expect('hints' in (payload as Record<string, unknown>)).toBe(false);
    // Only the hint COUNT leaks, not the text.
    expect(payload.hints_total).toBe(1);
    expect(serialized).not.toContain('"h"');
  });

  it('carries the FEN + prompt the client needs', () => {
    const payload = toPublicTask('asg-1', 'H_ROOK', task());
    expect(payload.fen).toBe('4k3/8/8/8/8/8/8/R3K3 w - - 0 1');
    expect(payload.prompt.en).toBe('Move the rook.');
    expect(payload.assignment_id).toBe('asg-1');
  });
});

describe('judgeSubmission — move validator', () => {
  it('accepts a legal move in the solution set', () => {
    expect(judgeSubmission(task(), { uci: 'a1a8' }).correct).toBe(true);
  });

  it('rejects a legal move that is NOT the intended answer', () => {
    const j = judgeSubmission(task(), { uci: 'a1a2' }); // legal rook move, wrong target
    expect(j.correct).toBe(false);
    expect(j.reason).toBe('wrong');
  });

  it('rejects an illegal move (legality checked before the answer set)', () => {
    const j = judgeSubmission(task(), { uci: 'a1b3' }); // not a rook move
    expect(j.correct).toBe(false);
    expect(j.reason).toBe('illegal_move');
  });

  it('rejects a malformed/empty submission', () => {
    expect(judgeSubmission(task(), {}).correct).toBe(false);
    expect(judgeSubmission(task(), { uci: '' }).reason).toBe('malformed');
  });

  it('is case-insensitive on the UCI', () => {
    expect(judgeSubmission(task(), { uci: 'A1A8' }).correct).toBe(true);
  });
});

describe('judgeSubmission — setup validator', () => {
  const setup = task({
    competency_code: 'H_SETUP',
    validator: 'setup',
    solution: { placement: 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR' },
    fen: 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w - - 0 1',
  });

  it('matches on the exact piece placement (placement field)', () => {
    expect(
      judgeSubmission(setup, { placement: 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR' }).correct,
    ).toBe(true);
  });

  it('extracts the placement field from a full FEN submission', () => {
    expect(
      judgeSubmission(setup, { fen: 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w - - 0 1' })
        .correct,
    ).toBe(true);
  });

  it('rejects a wrong placement', () => {
    const j = judgeSubmission(setup, { placement: 'rnbqkbnr/pppppppp/8/8/8/8/8/RNBQKBNR' });
    expect(j.correct).toBe(false);
    expect(j.reason).toBe('wrong');
  });

  it('rejects an empty placement', () => {
    expect(judgeSubmission(setup, {}).reason).toBe('malformed');
  });
});

describe('pickAssessmentTask', () => {
  const pool = [task({ id: 'a' }), task({ id: 'b' }), task({ id: 'c' }), task({ id: 'd' })];

  it('returns null for an empty pool', () => {
    expect(pickAssessmentTask([])).toBeNull();
  });

  it('prefers a task not recently seen', () => {
    const picked = pickAssessmentTask(pool, ['a', 'b', 'c'], 0);
    expect(picked?.id).toBe('d');
  });

  it('rotates deterministically through the pool', () => {
    expect(pickAssessmentTask(pool, [], 0)?.id).toBe('a');
    expect(pickAssessmentTask(pool, [], 1)?.id).toBe('b');
    expect(pickAssessmentTask(pool, [], 5)?.id).toBe('b'); // 5 % 4 = 1
  });

  it('falls back to the full pool when everything is recent', () => {
    const picked = pickAssessmentTask(pool, ['a', 'b', 'c', 'd'], 2);
    expect(picked?.id).toBe('c');
  });
});

describe('deriveSubmissionKey — idempotency key stability', () => {
  it('is identical for the same answer (double-click dedup)', () => {
    const k1 = deriveSubmissionKey('user_1', 'asg-1', { uci: 'a1a8' });
    const k2 = deriveSubmissionKey('user_1', 'asg-1', { uci: 'a1a8' });
    expect(k1).toBe(k2);
  });

  it('differs for a different answer on the same assignment', () => {
    const k1 = deriveSubmissionKey('user_1', 'asg-1', { uci: 'a1a8' });
    const k2 = deriveSubmissionKey('user_1', 'asg-1', { uci: 'a1a7' });
    expect(k1).not.toBe(k2);
  });

  it('is order-independent over submission keys (stable stringify)', () => {
    expect(stableStringify({ a: 1, b: 2 })).toBe(stableStringify({ b: 2, a: 1 }));
  });
});

describe('reward policy (data, not code)', () => {
  it('uses spec §6.2 values for a first competency pass', () => {
    const r = rewardForCompetencyPass(DEFAULT_REWARD_POLICY);
    expect(r).toEqual({ xp: 30, coins: 10 });
  });

  it('merges a partial stored config over the defaults', () => {
    const merged = normalizeRewardPolicy({ competency_pass_first: { xp: 99, coins: 1 } });
    expect(merged.competency_pass_first).toEqual({ xp: 99, coins: 1 });
    expect(merged.chapter_first).toEqual({ xp: 50, coins: 20 }); // default kept
  });

  it('falls back to defaults for a null/garbage config', () => {
    expect(normalizeRewardPolicy(null)).toEqual(DEFAULT_REWARD_POLICY);
    expect(normalizeRewardPolicy({ competency_pass_first: { xp: 'x' } }).competency_pass_first).toEqual(
      { xp: 30, coins: 10 },
    );
  });
});
