/**
 * @vitest-environment node
 *
 * Service IO tests for the Phase 4 Watchtower chapter. supabaseAdmin is mocked
 * with a scripted query builder + an `rpc` spy. Covers the chapter view (public
 * node payloads, NO solution; server-computed completion) and the node-completion
 * path (server judge + the once-per-chapter reward key + total-nodes contract).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

interface ScriptedResponse {
  data?: unknown;
  error?: unknown;
}
const scripts: Record<string, ScriptedResponse[]> = {};
const inserts: Array<{ table: string; payload: unknown }> = [];
const rpcCalls: Array<{ fn: string; args: Record<string, unknown> }> = [];
let rpcResponse: ScriptedResponse = { data: null, error: null };

function nextScript(table: string): ScriptedResponse {
  const q = scripts[table];
  return q && q.length ? (q.shift() as ScriptedResponse) : { data: null, error: null };
}
function makeBuilder(table: string) {
  const resolveNext = () => Promise.resolve(nextScript(table));
  const chain: Record<string, unknown> = {
    select: () => chain,
    eq: () => chain,
    in: () => chain,
    maybeSingle: () => resolveNext(),
    single: () => resolveNext(),
    insert: (payload: unknown) => {
      inserts.push({ table, payload });
      return chain;
    },
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

import { loadWatchtower, recordLearningNode } from '../watchtower-service';
import { WATCHTOWER_TOTAL_NODES } from '../review-rules';

const NODE = {
  id: 'w04-id',
  competency_code: 'H_QUEEN',
  family: 'W04',
  fen: '4k3/p7/8/8/8/8/8/R3K3 w - - 0 1',
  prompt_en: 'Capture the pawn.',
  prompt_ru: 'x',
  prompt_kk: 'x',
  solution: { moves: ['a1a7'] },
  validator: 'move',
  hints: [],
};

beforeEach(() => {
  for (const k of Object.keys(scripts)) delete scripts[k];
  inserts.length = 0;
  rpcCalls.length = 0;
  rpcResponse = { data: null, error: null };
});

describe('loadWatchtower — chapter view', () => {
  it('exposes node payloads with NO solution and server-computed completion', async () => {
    scripts.task_definition = [
      {
        data: [
          { ...NODE, id: 'w01', family: 'W01', solution: { squares: ['a1'] }, validator: 'squares' },
          { ...NODE, id: 'w04', family: 'W04' },
        ],
      },
    ];
    scripts.task_attempt = [{ data: [{ task_id: 'w01' }] }]; // W01 already done

    const view = await loadWatchtower('user_1');
    expect(view.total).toBe(WATCHTOWER_TOTAL_NODES);
    expect(view.completed_count).toBe(1);
    expect(view.chapter_complete).toBe(false);
    const w01 = view.nodes.find((n) => n.node === 'W01')!;
    expect(w01.completed).toBe(true);
    expect(view.nodes.find((n) => n.node === 'W04')!.completed).toBe(false);

    const serialized = JSON.stringify(view);
    expect(serialized).not.toContain('solution');
    expect(serialized).not.toContain('a1a7');
  });
});

describe('recordLearningNode — judge + chapter reward via one RPC', () => {
  it('404s for a non-Watchtower node family', async () => {
    const res = await recordLearningNode({
      ownerUserId: 'user_1', orgId: 'org-1', studentId: 'stu-1',
      node: 'W99', submission: { uci: 'a1a7' },
    });
    expect(res.status).toBe('not_found');
    expect(rpcCalls).toHaveLength(0);
  });

  function scriptHappy() {
    scripts.task_definition = [{ data: NODE }];
    scripts.task_assignment = [{ data: { id: 'asg-1' } }]; // insert().select().single()
    scripts.companion_reward_policy = [{ data: { config: { chapter_first: { xp: 50, coins: 20 } } } }];
  }

  it('judges server-side and drives the chapter RPC with the fixed key + node count', async () => {
    scriptHappy();
    rpcResponse = { data: { status: 'ok', correct: true, completed_count: 6, total: 6, chapter_complete: true, reward_granted: true, xp: 50, coins: 20 } };
    const res = await recordLearningNode({
      ownerUserId: 'user_1', orgId: 'org-1', studentId: 'stu-1',
      node: 'W04', submission: { uci: 'a1a7' },
    });

    expect(inserts.some((i) => i.table === 'task_assignment')).toBe(true);
    expect(rpcCalls).toHaveLength(1);
    const { fn, args } = rpcCalls[0];
    expect(fn).toBe('companion_complete_learning_node');
    expect(args.p_correct).toBe(true); // server judged
    expect(args.p_total_nodes).toBe(WATCHTOWER_TOTAL_NODES);
    expect(args.p_reward_key).toBe('companion:chapter:user_1:watchtower');
    expect(args.p_reward_xp).toBe(50); // from policy DATA
    expect(res).toMatchObject({ status: 'ok', chapter_complete: true, reward_granted: true, xp: 50 });
  });

  it('a wrong move is judged incorrect before the RPC', async () => {
    scriptHappy();
    rpcResponse = { data: { status: 'ok', correct: false, completed_count: 5, chapter_complete: false, reward_granted: false } };
    await recordLearningNode({
      ownerUserId: 'user_1', orgId: 'org-1', studentId: 'stu-1',
      node: 'W04', submission: { uci: 'a1a2' }, // legal but wrong
    });
    expect(rpcCalls[0].args.p_correct).toBe(false);
  });

  it('re-completing the chapter grants nothing (RPC idempotency, same reward key)', async () => {
    scriptHappy();
    rpcResponse = { data: { status: 'replayed', correct: true, completed_count: 6, chapter_complete: true, reward_granted: false, xp: 0, coins: 0 } };
    const res = await recordLearningNode({
      ownerUserId: 'user_1', orgId: 'org-1', studentId: 'stu-1',
      node: 'W04', submission: { uci: 'a1a7' },
    });
    expect(rpcCalls[0].args.p_reward_key).toBe('companion:chapter:user_1:watchtower');
    expect(res.chapter_complete).toBe(true);
    expect(res.reward_granted).toBe(false);
    expect(res.xp).toBe(0);
  });
});
