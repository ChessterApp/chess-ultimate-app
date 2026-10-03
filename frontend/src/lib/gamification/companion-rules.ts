/**
 * Companion — pure, framework-free rules (Phase 0 foundations).
 *
 * Deterministic, side-effect-free helpers shared by the (future) companion
 * service and API routes. No DB / Next imports, so they unit-test without a
 * database — mirroring economy.ts / items.ts. Server-authoritative IO will
 * live in a separate companion.ts module (architecture plan A6).
 */

// ---------------------------------------------------------------------------
// Feature flag — server-authoritative companion kill-switch (A6, R10)
// ---------------------------------------------------------------------------

/**
 * Whether the companion feature is enabled for an org. Reads
 * `companions_enabled === true` from the org's gamification_settings config —
 * this is the SERVER-authoritative check (the public `NEXT_PUBLIC_COMPANION_ENABLED`
 * env flag only gates UI mounting). Defaults to false so the feature stays dark
 * unless an org explicitly opts in.
 *
 * Accepts either the config object directly (`{ companions_enabled: true }`) or
 * a full settings row (`{ config: { companions_enabled: true } }`).
 */
export function isCompanionEnabled(settings: unknown): boolean {
  if (!settings || typeof settings !== 'object') return false;
  const maybeRow = settings as { config?: unknown };
  const config =
    maybeRow.config && typeof maybeRow.config === 'object' ? maybeRow.config : settings;
  return (config as { companions_enabled?: unknown }).companions_enabled === true;
}

// ---------------------------------------------------------------------------
// Idempotency namespace (plan A2)
// ---------------------------------------------------------------------------

/**
 * Namespaced idempotency key for companion ledger writes. The key space is
 * GLOBAL and shared with `ce_result:*` / `streak:*` (plan A2), so every
 * companion write MUST carry the `companion:` prefix to avoid colliding with
 * sync-engine awards.
 *
 * Shape: `companion:<kind>:<owner>:<ref>`. All three parts must be non-empty.
 */
export function companionIdempotencyKey(kind: string, owner: string, ref: string): string {
  const parts: Record<string, string> = { kind, owner, ref };
  for (const [name, value] of Object.entries(parts)) {
    if (typeof value !== 'string' || value.trim() === '') {
      throw new Error(`companionIdempotencyKey: "${name}" must be a non-empty string`);
    }
  }
  return `companion:${kind}:${owner}:${ref}`;
}
