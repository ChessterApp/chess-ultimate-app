/**
 * Companion — server-authoritative persistence (Phase 1, service-role IO).
 *
 * Thin wrappers over `supabaseAdmin` for the companion surface: the per-org
 * server flag check, loading the companion view (row + competency ring), and
 * persisting the "choose your egg" onboarding choice. All reads/writes are
 * owner-keyed by the Clerk `owner_user_id` (plan A3). No coin logic lives here —
 * nothing educational is ever coin-gated (R1).
 */
import 'server-only';
import { supabaseAdmin } from '@/lib/supabase-admin';
import { companionIdempotencyKey, isCompanionEnabled } from '@/lib/gamification/companion-rules';
import {
  type CompanionStage,
  type CompetencyProgress,
  HATCH_SPECIES_DEFAULT,
  MASTERY_TARGET_CORRECT,
  buildCompetencyRing,
  hatchProgress,
  isHatchReady,
  isValidEggVariant,
} from './state';
import { rewardForHatch } from './assessment';
import { loadRewardPolicy } from './assessment-service';

/**
 * Server-authoritative flag: is the companion feature switched on for this org?
 * Reads the raw `gamification_settings.config` (NOT the normalized economy
 * config, which is typed and would drop the key) and checks `companions_enabled`
 * via the shared helper. Defaults false — the feature stays dark per org until
 * explicitly opted in (R10, plan A6).
 */
export async function isCompanionEnabledForOrg(orgId: string): Promise<boolean> {
  const { data } = await supabaseAdmin
    .from('gamification_settings')
    .select('config')
    .eq('organization_id', orgId)
    .maybeSingle();
  return isCompanionEnabled(data);
}

export interface CompanionRow {
  species: string | null;
  name: string | null;
  stage: CompanionStage;
  hatched_at: string | null;
}

export interface CompetencyRingEntry extends CompetencyProgress {
  title_en: string;
  title_ru: string;
  title_kk: string;
  sort_order: number;
}

export interface CompanionView {
  /** Null until the kid chooses an egg (no companion row yet). */
  companion: CompanionRow | null;
  competencies: CompetencyRingEntry[];
  hatch_ready: boolean;
  /** 0..1 fraction of competencies demonstrated. */
  hatch_progress: number;
}

interface CompetencyDefRow {
  code: string;
  title_en: string;
  title_ru: string;
  title_kk: string;
  sort_order: number;
}

/**
 * Load the full companion view for one owner: their companion row (if any), the
 * active competency catalog, and the SM-2 mastery progress overlaid as the ring.
 * Read-only; safe to call on every page load.
 */
export async function loadCompanionView(ownerUserId: string): Promise<CompanionView> {
  const [companionRes, defsRes, masteryRes] = await Promise.all([
    supabaseAdmin
      .from('companion')
      .select('species,name,stage,hatched_at')
      .eq('owner_user_id', ownerUserId)
      .maybeSingle(),
    supabaseAdmin
      .from('competency_definition')
      .select('code,title_en,title_ru,title_kk,sort_order')
      .eq('active', true)
      .order('sort_order', { ascending: true }),
    supabaseAdmin
      .from('mastery_state')
      .select('competency_code,times_correct')
      .eq('owner_user_id', ownerUserId),
  ]);

  const companion = (companionRes.data as CompanionRow | null) ?? null;
  const defs = (defsRes.data as CompetencyDefRow[] | null) ?? [];
  const mastery = (masteryRes.data as { competency_code: string; times_correct: number }[] | null) ?? [];

  const stage: CompanionStage = companion?.stage ?? 'egg';
  const ring = buildCompetencyRing(
    defs.map((d) => d.code),
    mastery,
  );
  const byCode = new Map(ring.map((r) => [r.code, r]));

  const competencies: CompetencyRingEntry[] = defs.map((d) => {
    const prog = byCode.get(d.code)!;
    return {
      ...prog,
      title_en: d.title_en,
      title_ru: d.title_ru,
      title_kk: d.title_kk,
      sort_order: d.sort_order,
    };
  });

  return {
    companion,
    competencies,
    hatch_ready: isHatchReady(ring, stage),
    hatch_progress: hatchProgress(ring),
  };
}

export type ChooseEggResult =
  | { status: 'ok'; companion: CompanionRow }
  | { status: 'invalid_species' }
  | { status: 'already_hatched' };

/**
 * Persist the "choose your egg" onboarding choice. Upserts the single companion
 * row for the owner (owner_user_id is UNIQUE), storing the chosen variant as the
 * species while the companion stays in the `egg` stage. Idempotent — re-choosing
 * simply overwrites the species. Refuses to re-pick once the egg has hatched.
 */
export async function chooseEgg(ownerUserId: string, species: string): Promise<ChooseEggResult> {
  if (!isValidEggVariant(species)) return { status: 'invalid_species' };

  const { data: existing } = await supabaseAdmin
    .from('companion')
    .select('stage')
    .eq('owner_user_id', ownerUserId)
    .maybeSingle();
  if (existing && (existing as { stage: CompanionStage }).stage === 'hatched') {
    return { status: 'already_hatched' };
  }

  const { data, error } = await supabaseAdmin
    .from('companion')
    .upsert(
      { owner_user_id: ownerUserId, species, stage: 'egg' },
      { onConflict: 'owner_user_id' },
    )
    .select('species,name,stage,hatched_at')
    .single();

  if (error || !data) throw error ?? new Error('chooseEgg: upsert returned no row');
  return { status: 'ok', companion: data as CompanionRow };
}

// ---------------------------------------------------------------------------
// hatchCompanion — the atomic, idempotent hatch (Phase 3). Delegates ALL
// persistence + readiness re-check + reward/entitlement/event to the
// hatch_companion RPC (one transaction). Readiness is re-verified server-side
// from authoritative evidence; the client's hatch_ready flag is never trusted.
// Hatching is a REWARD, never coin-gated (R1).
// ---------------------------------------------------------------------------

export type HatchResult =
  | {
      status: 'ok' | 'already_hatched';
      companion: CompanionRow;
      reward_granted: boolean;
      xp: number;
      coins: number;
      starter_granted: boolean;
    }
  | { status: 'not_ready'; demonstrated: number; required: number };

export async function hatchCompanion(params: {
  ownerUserId: string;
  orgId: string;
  studentId: string;
  /** Already sanitized by the route (sanitizeCompanionName). */
  name: string;
}): Promise<HatchResult> {
  const { ownerUserId, orgId, studentId, name } = params;

  const reward = rewardForHatch(await loadRewardPolicy());
  const rewardKey = companionIdempotencyKey('hatch', ownerUserId, 'v1');

  const { data, error } = await supabaseAdmin.rpc('hatch_companion', {
    p_owner: ownerUserId,
    p_org: orgId,
    p_student: studentId,
    p_name: name,
    p_species_default: HATCH_SPECIES_DEFAULT,
    p_mastery_target: MASTERY_TARGET_CORRECT,
    p_reward_xp: reward.xp,
    p_reward_coins: reward.coins,
    p_reward_key: rewardKey,
  });
  if (error) throw new Error(error.message);

  const r = (data ?? {}) as Record<string, unknown>;
  if (r.status === 'not_ready') {
    return {
      status: 'not_ready',
      demonstrated: Number(r.demonstrated ?? 0),
      required: Number(r.required ?? 0),
    };
  }
  return {
    status: (r.status as 'ok' | 'already_hatched') ?? 'ok',
    companion: (r.companion as CompanionRow) ?? null,
    reward_granted: !!r.reward_granted,
    xp: Number(r.xp ?? 0),
    coins: Number(r.coins ?? 0),
    starter_granted: !!r.starter_granted,
  };
}
