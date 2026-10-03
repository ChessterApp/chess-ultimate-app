/**
 * @vitest-environment node
 *
 * Service IO tests for the Phase 4 pull-based review path. supabaseAdmin is
 * mocked with a per-table scripted query builder + an `rpc` spy, so the due-queue
 * read (no solution fields), the server-authoritative judge, the ladder
 * scheduling, and the once-per-occurrence reward key are exercised without a DB.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

interface ScriptedResponse {
  data?: unknown;
  error?: unknown;
}
const scripts: Record<string, ScriptedResponse[]> = {};
const reads: string[] = [];
const rpcCalls: Array<{ fn: string; args: Record<string, unknown> }> = [];
let rpcResponse: ScriptedResponse = { data: null, error: null };

function nextScript(table: string): ScriptedResponse {
  const q = scripts[table];
  return q && q.length ? (q.shift() as ScriptedResponse) : { data: null, error: null };
}
function makeBuilder(table: string) {
  const resolveNext = () => {
    reads.push(table);
    return Promise.resolve(nextScript(table));
  };
  const chain: Record<string, unknown> = {
    select: () => chain,
    eq: () => chain,
    in: () => chain,
    or: () => chain,
    order: () => chain,
    limit: () => resolveNext(),
    maybeSingle: () => resolveNext(),
    single: () => resolveNext(),
    then: (onF: (v: ScriptedResponse) => unknown, onR?: (e: unknown) => unknown) =>
      resolveNext().then(onF, onR),
  };
  return chain;
}
vi.mock('@/lib/supabase-admin', () => ({
  supabaseAdmin: {
    from: (t: string) => makeBuilder(t),
    rpc: (fn: string, args: Record<string, unknown>) => {
      rpcCalls.push({ fn, args });
      return Promise.resolve(rpcResponse);
    },
  },
}));

import { loadDueReviews, recordReview, POLICY_VERSION } from '../review-service';

const LADDER_ROW = { data: { config: { review_ladder: [1, 3, 7, 14], due_review: { xp: 15, coins: 5 } } } };
const REVIEW_TASK = {
  id: 'task-1',
  competency_code: 'H_ROOK',
  family: 'H_ROOK_T1',
  fen: '4k3/8/8/8/8/8/8/R3K3 w - - 0 1',
  prompt_en: 'Move the rook.',
  prompt_ru: 'x',
  prompt_kk: 'x',
  solution: { moves: ['a1a8'] },
  validator: 'move',
  hints: [],
};

beforeEach(() => {
  for (const k of Object.keys(scripts)) delete scripts[k];
  reads.length = 0;
  rpcCalls.length = 0;
  rpcResponse = { data: null, error: null };
});

describe('loadDueReviews — pull-based due queue', () => {
  it('returns due items (null or past) with NO solution fields, skips future', () => {
    const now = new Date('2026-01-10T00:00:00.000Z');
    scripts.mastery_state = [
      {
        data: [
          { competency_code: 'H_ROOK', interval_days: 0, next_review_at: null }, // due (null)
          { competency_code: 'H_KING', interval_days: 3, next_review_at: '2026-01-05T00:00:00Z' }, // due (past)
          { competency_code: 'H_PAWN', interval_days: 7, next_review_at: '2026-02-01T00:00:00Z' }, // future
        ],
      },
    ];
    scripts.companion_reward_policy = [LADDER_ROW];
    scripts.competency_definition = [
      {
        data: [
          { code: 'H_ROOK', title_en: 'The Rook', title_ru: 'Ладья', title_kk: 'Тура', sort_order: 2 },
          { code: 'H_KING', title_en: 'The King', title_ru: 'Король', title_kk: 'Патша', sort_order: 6 },
        ],
      },
    ];

    return loadDueReviews('user_1', now).then((due) => {
      expect(due.map((d) => d.competency)).toEqual(['H_KING', 'H_ROOK']); // sorted, future excluded
      expect(due.find((d) => d.competency === 'H_KING')!.rung).toBe(2); // interval 3 ⇒ rung 2
      const serialized = JSON.stringify(due);
      expect(serialized).not.toContain('solution');
      expect(serialized).not.toContain('a1a8');
    });
  });

  it('returns empty when nothing is due', () => {
    scripts.mastery_state = [
      { data: [{ competency_code: 'H_ROOK', interval_days: 7, next_review_at: '2099-01-01T00:00:00Z' }] },
    ];
    scripts.companion_reward_policy = [LADDER_ROW];
    return loadDueReviews('user_1', new Date('2026-01-10T00:00:00.000Z')).then((due) =>
      expect(due).toEqual([]),
    );
  });
});

describe('recordReview — judge + schedule + reward via one RPC', () => {
  function scriptHappy(masteryRow: unknown) {
    scripts.task_assignment = [
      {
        data: {
          id: 'asg-1',
          owner_user_id: 'user_1',
          task_id: 'task-1',
          competency_code: 'H_ROOK',
          mode: 'review',
          assistance_used: false,
        },
      },
    ];
    scripts.task_definition = [{ data: REVIEW_TASK }];
    scripts.companion_reward_policy = [LADDER_ROW];
    scripts.mastery_state = [{ data: masteryRow }];
  }

  it('404s when the assignment is missing / not owned', async () => {
    scripts.task_assignment = [{ data: null }];
    const res = await recordReview({
      ownerUserId: 'user_1', orgId: 'org-1', studentId: 'stu-1',
      assignmentId: 'x', submission: { uci: 'a1a8' },
    });
    expect(res.status).toBe('not_found');
    expect(rpcCalls).toHaveLength(0);
  });

  it('rejects a non-review assignment', async () => {
    scripts.task_assignment = [
      { data: { id: 'asg-1', owner_user_id: 'user_1', task_id: 'task-1', competency_code: 'H_ROOK', mode: 'assessment', assistance_used: false } },
    ];
    const res = await recordReview({
      ownerUserId: 'user_1', orgId: 'org-1', studentId: 'stu-1',
      assignmentId: 'asg-1', submission: { uci: 'a1a8' },
    });
    expect(res.status).toBe('invalid_mode');
    expect(rpcCalls).toHaveLength(0);
  });

  it('a correct first review advances to rung 1 (1 day) and keys the reward by the "initial" occurrence', async () => {
    scriptHappy({ interval_days: 0, next_review_at: null });
    rpcResponse = { data: { status: 'ok', correct: true, assistance_used: false, interval_days: 1, times_correct: 1, reward_granted: true, xp: 15, coins: 5 } };
    const now = new Date('2026-01-01T00:00:00.000Z');
    const res = await recordReview({
      ownerUserId: 'user_1', orgId: 'org-1', studentId: 'stu-1',
      assignmentId: 'asg-1', submission: { uci: 'a1a8' }, now,
    });
    expect(rpcCalls).toHaveLength(1);
    const { fn, args } = rpcCalls[0];
    expect(fn).toBe('companion_record_review');
    expect(args.p_correct).toBe(true);
    expect(args.p_interval_days).toBe(1);
    expect(args.p_next_review_at).toBe(new Date(now.getTime() + 86_400_000).toISOString());
    expect(args.p_reward_key).toBe('companion:review:user_1:H_ROOK:initial');
    expect(args.p_policy_version).toBe(POLICY_VERSION);
    expect(args.p_reward_xp).toBe(15); // from policy DATA
    expect(res).toMatchObject({ status: 'ok', correct: true, reward_granted: true, xp: 15 });
  });

  it('advances the ladder 3→7 on a correct review and dates the reward key to the due occurrence', async () => {
    scriptHappy({ interval_days: 3, next_review_at: '2026-01-04T09:00:00.000Z' });
    rpcResponse = { data: { status: 'ok', correct: true, interval_days: 7, reward_granted: true, xp: 15, coins: 5 } };
    const now = new Date('2026-01-04T12:00:00.000Z');
    await recordReview({
      ownerUserId: 'user_1', orgId: 'org-1', studentId: 'stu-1',
      assignmentId: 'asg-1', submission: { uci: 'a1a8' }, now,
    });
    const { args } = rpcCalls[0];
    expect(args.p_interval_days).toBe(7);
    expect(args.p_reward_key).toBe('companion:review:user_1:H_ROOK:2026-01-04');
  });

  it('a wrong move resets the ladder to 1 day and earns nothing', async () => {
    scriptHappy({ interval_days: 7, next_review_at: '2026-01-04T00:00:00.000Z' });
    rpcResponse = { data: { status: 'ok', correct: false, interval_days: 1, reward_granted: false, xp: 0, coins: 0 } };
    const now = new Date('2026-01-05T00:00:00.000Z');
    await recordReview({
      ownerUserId: 'user_1', orgId: 'org-1', studentId: 'stu-1',
      assignmentId: 'asg-1', submission: { uci: 'a1a2' }, now, // legal but wrong
    });
    const { args } = rpcCalls[0];
    expect(args.p_correct).toBe(false);
    expect(args.p_interval_days).toBe(1); // reset to rung 1
  });

  it('a double-submit replays (same submission + reward key) and grants nothing', async () => {
    scriptHappy({ interval_days: 0, next_review_at: null });
    rpcResponse = { data: { status: 'replayed', correct: true, interval_days: 1, reward_granted: false, xp: 0, coins: 0 } };
    const first = await recordReview({ ownerUserId: 'user_1', orgId: 'org-1', studentId: 'stu-1', assignmentId: 'asg-1', submission: { uci: 'a1a8' } });
    const key1 = rpcCalls[0].args.p_reward_key;

    scriptHappy({ interval_days: 0, next_review_at: null });
    await recordReview({ ownerUserId: 'user_1', orgId: 'org-1', studentId: 'stu-1', assignmentId: 'asg-1', submission: { uci: 'a1a8' } });
    const key2 = rpcCalls[1].args.p_reward_key;

    expect(key1).toBe(key2); // same occurrence ⇒ one reward via the UNIQUE ledger key
    expect(first.status).toBe('replayed');
    expect(first.reward_granted).toBe(false);
  });

  it('never reads a coin balance / wallet on the review path (R1)', async () => {
    scriptHappy({ interval_days: 0, next_review_at: null });
    rpcResponse = { data: { status: 'ok', correct: true, reward_granted: false } };
    await recordReview({ ownerUserId: 'user_1', orgId: 'org-1', studentId: 'stu-1', assignmentId: 'asg-1', submission: { uci: 'a1a8' } });
    expect(reads).not.toContain('coin_ledger');
    expect(reads).not.toContain('player_gamification');
    expect(reads).not.toContain('player_items');
  });
});
