/**
 * Intercom support widget — paying-tier gating (PRD §11.3 #5).
 *
 * Intercom is enabled for paying tiers only (Growth / Pro / Enterprise).
 * Starter tier and unpaid orgs get the existing static help center.
 *
 * Pure helpers live here so unit tests can verify gating without booting
 * a JSDOM environment. The actual widget mount is in `<IntercomWidget />`.
 */

export type Tier = 'starter' | 'growth' | 'pro' | 'enterprise';

const PAYING_TIERS: ReadonlySet<Tier> = new Set(['growth', 'pro', 'enterprise']);

export function isPayingTier(tier: string | null | undefined): boolean {
  if (!tier) return false;
  return PAYING_TIERS.has(tier as Tier);
}

export interface IntercomBootSettings {
  app_id: string;
  user_id?: string;
  email?: string;
  name?: string;
  company?: {
    id: string;
    name?: string;
    plan?: string;
  };
}

export interface IntercomContext {
  appId?: string | null;
  tier?: string | null;
  userId?: string | null;
  email?: string | null;
  name?: string | null;
  orgId?: string | null;
  orgName?: string | null;
}

/**
 * Build the Intercom boot settings or return null if the widget should
 * not boot (free tier, missing app_id, etc.).
 *
 * Caller is responsible for actually invoking `window.Intercom('boot', …)`.
 */
export function buildBootSettings(
  ctx: IntercomContext,
): IntercomBootSettings | null {
  if (!ctx.appId) return null;
  if (!isPayingTier(ctx.tier)) return null;

  const settings: IntercomBootSettings = { app_id: ctx.appId };
  if (ctx.userId) settings.user_id = ctx.userId;
  if (ctx.email) settings.email = ctx.email;
  if (ctx.name) settings.name = ctx.name;
  if (ctx.orgId) {
    settings.company = {
      id: ctx.orgId,
      ...(ctx.orgName ? { name: ctx.orgName } : {}),
      ...(ctx.tier ? { plan: ctx.tier } : {}),
    };
  }
  return settings;
}
