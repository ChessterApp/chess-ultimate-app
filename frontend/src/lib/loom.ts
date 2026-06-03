/**
 * Loom embed helpers (PRD §11.3 #5).
 *
 * Loom videos are embedded in:
 *   - the wizard step 6 (post-payment activation)
 *   - the post-onboarding checklist on /admin/dashboard
 *
 * Loom share URLs take the form
 *   https://www.loom.com/share/<id>
 * and the embeddable iframe URL is
 *   https://www.loom.com/embed/<id>
 *
 * `loomEmbedUrl()` accepts either form and returns the canonical embed
 * URL. It returns null for inputs that don't match.
 */

const LOOM_SHARE_RE = /^https?:\/\/(?:www\.)?loom\.com\/share\/([A-Za-z0-9]+)(?:[/?#]|$)/;
const LOOM_EMBED_RE = /^https?:\/\/(?:www\.)?loom\.com\/embed\/([A-Za-z0-9]+)(?:[/?#]|$)/;
const LOOM_ID_RE = /^[A-Za-z0-9]{8,}$/;

export function loomEmbedUrl(input: string | null | undefined): string | null {
  if (!input) return null;
  const trimmed = input.trim();
  if (!trimmed) return null;

  const share = trimmed.match(LOOM_SHARE_RE);
  if (share) return `https://www.loom.com/embed/${share[1]}`;
  const embed = trimmed.match(LOOM_EMBED_RE);
  if (embed) return `https://www.loom.com/embed/${embed[1]}`;
  if (LOOM_ID_RE.test(trimmed)) return `https://www.loom.com/embed/${trimmed}`;
  return null;
}

export interface LoomConfig {
  // Welcome video embedded in the activation screen + dashboard checklist
  welcomeUrl: string | null;
  // Tier-specific deep-dive videos
  tierUrls: Partial<Record<'starter' | 'growth' | 'pro' | 'enterprise', string>>;
}

/**
 * Pure config builder — reads from env-style values. Centralized here so
 * tests can verify the env→URL pipeline without booting a component.
 */
export function buildLoomConfig(env: Record<string, string | undefined>): LoomConfig {
  return {
    welcomeUrl: loomEmbedUrl(env.NEXT_PUBLIC_LOOM_WELCOME_URL),
    tierUrls: {
      ...(env.NEXT_PUBLIC_LOOM_STARTER_URL && {
        starter: loomEmbedUrl(env.NEXT_PUBLIC_LOOM_STARTER_URL) || undefined,
      }),
      ...(env.NEXT_PUBLIC_LOOM_GROWTH_URL && {
        growth: loomEmbedUrl(env.NEXT_PUBLIC_LOOM_GROWTH_URL) || undefined,
      }),
      ...(env.NEXT_PUBLIC_LOOM_PRO_URL && {
        pro: loomEmbedUrl(env.NEXT_PUBLIC_LOOM_PRO_URL) || undefined,
      }),
      ...(env.NEXT_PUBLIC_LOOM_ENTERPRISE_URL && {
        enterprise: loomEmbedUrl(env.NEXT_PUBLIC_LOOM_ENTERPRISE_URL) || undefined,
      }),
    },
  };
}

export function pickLoomForTier(
  config: LoomConfig,
  tier: string | null | undefined,
): string | null {
  if (tier && config.tierUrls[tier as keyof LoomConfig['tierUrls']]) {
    return config.tierUrls[tier as keyof LoomConfig['tierUrls']] as string;
  }
  return config.welcomeUrl;
}
