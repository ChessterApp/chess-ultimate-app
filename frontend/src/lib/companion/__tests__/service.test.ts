/**
 * @vitest-environment node
 *
 * Service IO tests for the companion persistence layer. The Supabase admin
 * client is mocked with a per-table scripted query builder (same idiom as
 * pending-registration.test.ts) so the owner-keyed reads/writes exercise real
 * code without a database.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

interface ScriptedResponse {
  data?: unknown;
  error?: unknown;
}

const scripts: Record<string, ScriptedResponse[]> = {};
const upserted: Array<{ table: string; payload: unknown; opts: unknown }> = [];

function nextScript(table: string): ScriptedResponse {
  const q = scripts[table];
  if (!q || q.length === 0) return { data: null, error: null };
  return q.shift() as ScriptedResponse;
}

function makeBuilder(table: string) {
  const resolveNext = () => Promise.resolve(nextScript(table));
  const chain: Record<string, unknown> = {
    select: () => chain,
    eq: () => chain,
    order: () => resolveNext(),
    maybeSingle: () => resolveNext(),
    single: () => resolveNext(),
    upsert: (payload: unknown, opts: unknown) => {
      upserted.push({ table, payload, opts });
      return chain;
    },
    then: (onF: (v: ScriptedResponse) => unknown, onR?: (e: unknown) => unknown) =>
      resolveNext().then(onF, onR),
  };
  return chain;
}

vi.mock('@/lib/supabase-admin', () => ({
  supabaseAdmin: { from: (table: string) => makeBuilder(table) },
}));

import {
  isCompanionEnabledForOrg,
  loadCompanionView,
  chooseEgg,
} from '../service';

beforeEach(() => {
  for (const k of Object.keys(scripts)) delete scripts[k];
  upserted.length = 0;
});

describe('isCompanionEnabledForOrg', () => {
  it('true only when the org config opts in', async () => {
    scripts.gamification_settings = [{ data: { config: { companions_enabled: true } } }];
    expect(await isCompanionEnabledForOrg('org-1')).toBe(true);
  });

  it('false when disabled or the settings row is missing', async () => {
    scripts.gamification_settings = [{ data: { config: { companions_enabled: false } } }];
    expect(await isCompanionEnabledForOrg('org-1')).toBe(false);
    scripts.gamification_settings = [{ data: null }];
    expect(await isCompanionEnabledForOrg('org-1')).toBe(false);
  });
});

describe('loadCompanionView', () => {
  it('overlays mastery onto the competency catalog and gates the hatch', async () => {
    scripts.companion = [{ data: { species: 'fox', name: null, stage: 'egg', hatched_at: null } }];
    scripts.competency_definition = [
      {
        data: [
          { code: 'H_ROOK', title_en: 'The Rook', title_ru: 'Ладья', title_kk: 'Тура', sort_order: 1 },
          { code: 'H_KING', title_en: 'The King', title_ru: 'Король', title_kk: 'Патша', sort_order: 2 },
        ],
      },
    ];
    scripts.mastery_state = [{ data: [{ competency_code: 'H_ROOK', times_correct: 3 }] }];

    const view = await loadCompanionView('user_1');
    expect(view.companion?.species).toBe('fox');
    expect(view.competencies).toHaveLength(2);
    expect(view.competencies[0].code).toBe('H_ROOK');
    expect(view.competencies[0].demonstrated).toBe(true);
    expect(view.competencies[0].title_en).toBe('The Rook');
    expect(view.competencies[1].demonstrated).toBe(false);
    expect(view.hatch_ready).toBe(false); // only 1/2 demonstrated
    expect(view.hatch_progress).toBeCloseTo(0.5);
  });

  it('returns a null companion when no egg has been chosen', async () => {
    scripts.companion = [{ data: null }];
    scripts.competency_definition = [{ data: [] }];
    scripts.mastery_state = [{ data: [] }];
    const view = await loadCompanionView('user_1');
    expect(view.companion).toBeNull();
    expect(view.competencies).toEqual([]);
    expect(view.hatch_ready).toBe(false);
  });
});

describe('chooseEgg', () => {
  it('rejects an invalid species without touching the DB', async () => {
    const res = await chooseEgg('user_1', 'unicorn');
    expect(res.status).toBe('invalid_species');
    expect(upserted).toHaveLength(0);
  });

  it('refuses to re-pick once hatched', async () => {
    scripts.companion = [{ data: { stage: 'hatched' } }];
    const res = await chooseEgg('user_1', 'fox');
    expect(res.status).toBe('already_hatched');
    expect(upserted).toHaveLength(0);
  });

  it('upserts the chosen egg in the egg stage (idempotent on owner)', async () => {
    scripts.companion = [
      { data: null }, // existence check — no row yet
      { data: { species: 'owl', name: null, stage: 'egg', hatched_at: null } }, // upsert .single()
    ];
    const res = await chooseEgg('user_1', 'owl');
    expect(res.status).toBe('ok');
    expect(upserted).toHaveLength(1);
    expect(upserted[0].payload).toMatchObject({ owner_user_id: 'user_1', species: 'owl', stage: 'egg' });
    expect(upserted[0].opts).toMatchObject({ onConflict: 'owner_user_id' });
  });
});
