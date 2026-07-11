import type { Bot, BotTier } from '@/data/bots'
import { TIER_LABELS, TIER_WORLDS } from '@/data/bots'

/**
 * Minimal shape of a next-intl translator scoped to the `bots` namespace.
 * We only use plain lookups plus `has()` for the missing-key fallback.
 */
type Translator = ((
  key: string,
  values?: Record<string, string | number>,
) => string) & { has: (key: string) => boolean }

/** Localized bot description, falling back to the raw bots.ts string. */
export const botDescription = (t: Translator, bot: Bot): string =>
  t.has(`${bot.id}.description`) ? t(`${bot.id}.description`) : bot.description

/** Localized bot play style, falling back to the raw bots.ts string. */
export const botPlayStyle = (t: Translator, bot: Bot): string =>
  t.has(`${bot.id}.playStyle`) ? t(`${bot.id}.playStyle`) : bot.playStyle

/** Localized tier label, falling back to the hardcoded TIER_LABELS. */
export const tierLabel = (t: Translator, tier: BotTier): string =>
  t.has(`tiers.${tier}`) ? t(`tiers.${tier}`) : TIER_LABELS[tier]

/**
 * Localized play-screen UI string under `bots.play.*`, falling back to the raw
 * English default when the key is absent. Keeps new play-page copy on the same
 * i18n mechanism the bot components already use.
 */
export const playText = (
  t: Translator,
  key: string,
  fallback: string,
  values?: Record<string, string | number>,
): string => (t.has(`play.${key}`) ? t(`play.${key}`, values) : fallback)

/** Localized world name for a tier, falling back to the i18n key itself. */
export const worldName = (t: Translator, tier: BotTier): string => {
  const key = TIER_WORLDS[tier].key
  return t.has(`worlds.${key}`) ? t(`worlds.${key}`) : `worlds.${key}`
}
