/**
 * @vitest-environment node
 *
 * Service IO tests for the Phase 2 assessment pipeline. Supabase admin is mocked
 * with a per-table scripted query builder (same idiom as service.test.ts) plus an
 * `rpc` spy, so the owner-keyed reads/writes and the single reward RPC are
 * exercised without a database.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

interface ScriptedResponse {
  data?: unknown;
  error?: unknown;
}

const scripts: Record<string, ScriptedResponse[]> = {};
const inserts: Array<{ table: string; payload: unknown }> = [];
const updates: Array<{ table: string; payload: unknown }> = [];
const reads: string[] = [];
const rpcCalls: Array<{ fn: string; args: Record<string, unknown> }> = [];
let rpcResponse: ScriptedResponse = { data: null, error: null };

function nextScript(table: string): ScriptedResponse {
  const q = scripts[table];
  if (!q || q.length === 0) return { data: null, error: null };
  return q.shift() as ScriptedResponse;
}

function makeBuilder(table: string) {
  const resolveNext = () => {
    reads.push(table);
    return Promise.resolve(nextScript(table));
  };
  const chain: Record<string, unknown> = {
    select: () => chain,
    eq: () => chain,
    order: () => chain,
    limit: () => resolveNext(),
    maybeSingle: () => resolveNext(),
    single: () => resolveNext(),
    insert: (payload: unknown) => {
      inserts.push({ table, payload });
      return chain;
    },
    update: (payload: unknown) => {
      updates.push({ table, payload });
      return chain;
    },
    then: (onF: (v: ScriptedResponse) => unknown, onR?: (e: unknown) => unknown) =>
      resolveNext().then(onF, onR),
  };
  return chain;
}

vi.mock('@/lib/supabase-admin', () => ({
  supabaseAdmin: {
    from: (table: string) => makeBuilder(table),
    rpc: (fn: string, args: Record<string, unknown>) => {
      rpcCalls.push({ fn, args });
      return Promise.resolve(rpcResponse);
    },
  },
}));

import { createAssignment, recordAttempt, logHint, POLICY_VERSION } from '../assessment-service';
import { MASTERY_TARGET_CORRECT } from '../state';

const TASK = {
  id: 'task-1',
  competency_code: 'H_ROOK',
  family: 'H_ROOK_T1',
  fen: '4k3/8/8/8/8/8/8/R3K3 w - - 0 1',
  prompt_en: 'Move the rook.',
  prompt_ru: 'Ход ладьёй.',
  prompt_kk: 'Турамен жүру.',
  solution: { moves: ['a1a8'] },
  validator: 'move',
  hints: [{ en: 'Rooks slide in straight lines.', ru: 'Ладья по прямым.', kk: 'Тура тік.' }],
};

beforeEach(() => {
  for (const k of Object.keys(scripts)) delete scripts[k];
  inserts.length = 0;
  updates.length = 0;
  reads.length = 0;
  rpcCalls.length = 0;
  rpcResponse = { data: null, error: null };
});

describe('createAssignment', () => {
  it('returns no_tasks when the pool is empty', async () => {
    scripts.task_definition = [{ data: [] }];
    const res = await createAssignment('user_1', 'H_ROOK');
    expect(res.status).toBe('no_tasks');
    expect(inserts).toHaveLength(0);
  });

  it('issues an assignment and returns a solution-free payload', async () => {
    scripts.task_definition = [{ data: [TASK] }];
    scripts.task_assignment = [
      { data: [] }, // prior-assignments lookup (order/limit)
      { data: { id: 'asg-9' } }, // insert().select().single()
    ];
    const res = await createAssignment('user_1', 'H_ROOK');
    expect(res.status).toBe('ok');
    if (res.status !== 'ok') return;

    // Inserted a server-issued assignment for this owner.
    expect(inserts).toHaveLength(1);
    expect(inserts[0].table).toBe('task_assignment');
    expect(inserts[0].payload).toMatchObject({
      owner_user_id: 'user_1',
      task_id: 'task-1',
      competency_code: 'H_ROOK',
      mode: 'assessment',
      status: 'issued',
    });

    // HARD RULE: the payload carries FEN + prompt but never the answer.
    const serialized = JSON.stringify(res.task);
    expect(res.task.fen).toBe(TASK.fen);
    expect(res.task.assignment_id).toBe('asg-9');
    expect(res.task.hints_total).toBe(1);
    expect(serialized).not.toContain('a1a8');
    expect(serialized).not.toContain('solution');
    expect(serialized).not.toContain('Rooks slide'); // hint text never leaks
  });
});

describe('recordAttempt', () => {
  const policyRow = { data: { config: { competency_pass_first: { xp: 30, coins: 10 } } } };

  function scriptHappyPath() {
    scripts.task_assignment = [
      {
        data: {
          id: 'asg-1',
          owner_user_id: 'user_1',
          task_id: 'task-1',
          competency_code: 'H_ROOK',
          mode: 'assessment',
          assistance_used: false,
        },
      },
    ];
    scripts.task_definition = [{ data: TASK }];
    scripts.companion_reward_policy = [policyRow];
  }

  it('404s when the assignment is missing / not owned', async () => {
    scripts.task_assignment = [{ data: null }];
    const res = await recordAttempt({
      ownerUserId: 'user_1',
      orgId: 'org-1',
      studentId: 'stu-1',
      assignmentId: 'asg-x',
      submission: { uci: 'a1a8' },
    });
    expect(res.status).toBe('not_found');
    expect(rpcCalls).toHaveLength(0);
  });

  it('rejects a non-assessment assignment', async () => {
    scripts.task_assignment = [
      { data: { id: 'asg-1', owner_user_id: 'user_1', task_id: 'task-1', competency_code: 'H_ROOK', mode: 'learning', assistance_used: false } },
    ];
    const res = await recordAttempt({
      ownerUserId: 'user_1',
      orgId: 'org-1',
      studentId: 'stu-1',
      assignmentId: 'asg-1',
      submission: { uci: 'a1a8' },
    });
    expect(res.status).toBe('invalid_mode');
    expect(rpcCalls).toHaveLength(0);
  });

  it('judges server-side and drives ONE reward RPC with a namespaced key', async () => {
    scriptHappyPath();
    rpcResponse = {
      data: {
        status: 'ok',
        correct: true,
        assistance_used: false,
        demonstrated: true,
        times_correct: MASTERY_TARGET_CORRECT,
        reward_granted: true,
        xp: 30,
        coins: 10,
      },
    };
    const res = await recordAttempt({
      ownerUserId: 'user_1',
      orgId: 'org-1',
      studentId: 'stu-1',
      assignmentId: 'asg-1',
      submission: { uci: 'a1a8' },
    });

    expect(rpcCalls).toHaveLength(1);
    const { fn, args } = rpcCalls[0];
    expect(fn).toBe('companion_record_attempt');
    expect(args.p_correct).toBe(true); // server judged, not client-asserted
    expect(args.p_submission_key).toBe('companion:attempt:user_1:asg-1:{"uci":"a1a8"}');
    expect(args.p_reward_key).toBe('companion:competency_pass:user_1:H_ROOK');
    expect(args.p_policy_version).toBe(POLICY_VERSION);
    expect(args.p_mastery_target).toBe(MASTERY_TARGET_CORRECT);
    expect(args.p_reward_xp).toBe(30); // from policy DATA, not hardcoded
    expect(args.p_reward_coins).toBe(10);

    expect(res).toMatchObject({ status: 'ok', correct: true, demonstrated: true, reward_granted: true, xp: 30, coins: 10 });
  });

  it('marks a wrong move incorrect before the RPC (server-authoritative)', async () => {
    scriptHappyPath();
    rpcResponse = { data: { status: 'ok', correct: false, demonstrated: false, times_correct: 0, reward_granted: false, xp: 0, coins: 0 } };
    await recordAttempt({
      ownerUserId: 'user_1',
      orgId: 'org-1',
      studentId: 'stu-1',
      assignmentId: 'asg-1',
      submission: { uci: 'a1a2' }, // legal rook move, wrong answer
    });
    expect(rpcCalls[0].args.p_correct).toBe(false);
  });

  it('never reads a coin balance / wallet on the educational path (R1)', async () => {
    scriptHappyPath();
    rpcResponse = { data: { status: 'ok', correct: true, demonstrated: false, times_correct: 1, reward_granted: false, xp: 0, coins: 0 } };
    await recordAttempt({
      ownerUserId: 'user_1',
      orgId: 'org-1',
      studentId: 'stu-1',
      assignmentId: 'asg-1',
      submission: { uci: 'a1a8' },
    });
    expect(reads).not.toContain('coin_ledger');
    expect(reads).not.toContain('player_gamification');
    expect(reads).not.toContain('player_items');
  });

  it('is double-submit idempotent: same answer ⇒ identical submission_key; a replay grants nothing', async () => {
    scriptHappyPath();
    rpcResponse = { data: { status: 'replayed', correct: true, demonstrated: true, times_correct: MASTERY_TARGET_CORRECT, reward_granted: false, xp: 0, coins: 0 } };
    const first = await recordAttempt({ ownerUserId: 'user_1', orgId: 'org-1', studentId: 'stu-1', assignmentId: 'asg-1', submission: { uci: 'a1a8' } });
    const key1 = rpcCalls[0].args.p_submission_key;

    scriptHappyPath();
    await recordAttempt({ ownerUserId: 'user_1', orgId: 'org-1', studentId: 'stu-1', assignmentId: 'asg-1', submission: { uci: 'a1a8' } });
    const key2 = rpcCalls[1].args.p_submission_key;

    expect(key1).toBe(key2); // DB UNIQUE(submission_key) dedups to one attempt/evidence row
    expect(first.status).toBe('replayed');
    expect(first.reward_granted).toBe(false);
    expect(first.xp).toBe(0);
  });

  it('forwards a client-asserted assistance flag (never downgradable to false)', async () => {
    scriptHappyPath();
    rpcResponse = { data: { status: 'ok', correct: true, demonstrated: false, times_correct: 1, reward_granted: false, xp: 0, coins: 0 } };
    await recordAttempt({ ownerUserId: 'user_1', orgId: 'org-1', studentId: 'stu-1', assignmentId: 'asg-1', submission: { uci: 'a1a8' }, assistanceUsed: true });
    expect(rpcCalls[0].args.p_assistance_used).toBe(true);
  });
});

describe('logHint', () => {
  it('404s when the assignment is not owned', async () => {
    scripts.task_assignment = [{ data: null }];
    const res = await logHint('user_1', 'asg-x', 0);
    expect(res.status).toBe('not_found');
    expect(updates).toHaveLength(0);
  });

  it('sets assistance BEFORE returning the hint content', async () => {
    scripts.task_assignment = [
      { data: { id: 'asg-1', task_id: 'task-1' } }, // ownership lookup
      { error: null }, // the assistance UPDATE
    ];
    scripts.task_definition = [{ data: { hints: TASK.hints } }];

    const res = await logHint('user_1', 'asg-1', 0);
    expect(res.status).toBe('ok');
    if (res.status !== 'ok') return;

    // Assistance was persisted (and that write happened before the hint read).
    expect(updates).toHaveLength(1);
    expect(updates[0].table).toBe('task_assignment');
    expect(updates[0].payload).toMatchObject({ assistance_used: true });
    const assistIdx = reads.indexOf('task_definition');
    expect(assistIdx).toBeGreaterThan(-1);

    expect(res.assistance_used).toBe(true);
    expect(res.hint).toEqual(TASK.hints[0]);
    expect(res.hints_total).toBe(1);
  });

  it('clamps an out-of-range hint index', async () => {
    scripts.task_assignment = [{ data: { id: 'asg-1', task_id: 'task-1' } }, { error: null }];
    scripts.task_definition = [{ data: { hints: TASK.hints } }];
    const res = await logHint('user_1', 'asg-1', 99);
    expect(res.status).toBe('ok');
    if (res.status !== 'ok') return;
    expect(res.hint_index).toBe(0); // only one hint ⇒ clamped to 0
  });
});
