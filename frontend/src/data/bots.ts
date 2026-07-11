export type BotTier = 'beginner' | 'intermediate' | 'advanced' | 'master'

/** Signature palette for the "Hero Trading Cards" bot tiles. */
export interface BotColors {
  /** Border / accent color. */
  main: string
  /** Deep shade used for the name-banner gradient. */
  deep: string
  /** Soft tint used as the card background. */
  tint: string
}

export interface Bot {
  id: string
  name: string
  rating: number
  tier: BotTier
  description: string
  playStyle: string
  avatar?: string
  /** Emoji shown before the play-style label on the card chip. */
  emoji?: string
  /** Per-bot signature colors (beginner heroes); others fall back to a tier palette. */
  colors?: BotColors
}

export const TIER_COLORS: Record<BotTier, string> = {
  beginner: '#6B7280',
  intermediate: '#22C55E',
  advanced: '#3B82F6',
  master: '#F59E0B',
}

// Bright, distinct hues per tier for bots without a hand-picked signature palette.
// Cycled by the bot's position within its tier so cards stay visually varied.
export const TIER_PALETTES: Record<BotTier, BotColors[]> = {
  beginner: [
    { main: '#38BDF8', deep: '#0369A1', tint: '#EAF7FF' },
    { main: '#FB7185', deep: '#BE123C', tint: '#FFF0F2' },
    { main: '#4ADE80', deep: '#15803D', tint: '#EFFCF3' },
    { main: '#C084FC', deep: '#7E22CE', tint: '#F9F1FF' },
  ],
  intermediate: [
    { main: '#34D399', deep: '#047857', tint: '#ECFDF5' },
    { main: '#22D3EE', deep: '#0E7490', tint: '#ECFEFF' },
    { main: '#A3E635', deep: '#4D7C0F', tint: '#F7FEE7' },
    { main: '#2DD4BF', deep: '#0F766E', tint: '#F0FDFA' },
  ],
  advanced: [
    { main: '#60A5FA', deep: '#1D4ED8', tint: '#EFF6FF' },
    { main: '#818CF8', deep: '#4338CA', tint: '#EEF2FF' },
    { main: '#38BDF8', deep: '#0369A1', tint: '#EAF7FF' },
    { main: '#A78BFA', deep: '#6D28D9', tint: '#F5F3FF' },
  ],
  master: [
    { main: '#FBBF24', deep: '#B45309', tint: '#FFFBEB' },
    { main: '#FB923C', deep: '#C2410C', tint: '#FFF7ED' },
    { main: '#F472B6', deep: '#BE185D', tint: '#FDF2F8' },
    { main: '#F87171', deep: '#B91C1C', tint: '#FEF2F2' },
  ],
}

export const TIER_LABELS: Record<BotTier, string> = {
  beginner: 'Beginner',
  intermediate: 'Intermediate',
  advanced: 'Advanced',
  master: 'Master',
}

export const BOTS: Bot[] = [
  // Beginner tier (1100-1300)
  {
    id: 'luna-1100',
    name: 'Luna',
    rating: 1100,
    tier: 'beginner',
    description: 'Friendly and encouraging, perfect for your first games',
    playStyle: 'Patient',
    avatar: '/bots/luna.webp',
    emoji: '🌙',
    colors: { main: '#38BDF8', deep: '#0369A1', tint: '#EAF7FF' },
  },
  {
    id: 'rex-1200',
    name: 'Rex',
    rating: 1200,
    tier: 'beginner',
    description: 'Straightforward player learning the basics',
    playStyle: 'Solid',
    avatar: '/bots/rex.webp',
    emoji: '🧱',
    colors: { main: '#FB7185', deep: '#BE123C', tint: '#FFF0F2' },
  },
  {
    id: 'milo-1300',
    name: 'Milo',
    rating: 1300,
    tier: 'beginner',
    description: 'Casual player who loves a good game',
    playStyle: 'Relaxed',
    avatar: '/bots/milo.webp',
    emoji: '☕',
    colors: { main: '#4ADE80', deep: '#15803D', tint: '#EFFCF3' },
  },
  {
    id: 'zara-1300',
    name: 'Zara',
    rating: 1300,
    tier: 'beginner',
    description: 'Enthusiastic learner eager to improve',
    playStyle: 'Eager',
    avatar: '/bots/zara.webp',
    emoji: '✨',
    colors: { main: '#C084FC', deep: '#7E22CE', tint: '#F9F1FF' },
  },

  // Intermediate tier (1400-1600)
  {
    id: 'sven-1400',
    name: 'Sven',
    rating: 1400,
    tier: 'intermediate',
    description: 'Strategic thinker with solid fundamentals',
    playStyle: 'Strategic',
    emoji: '🧠',
  },
  {
    id: 'nina-1500',
    name: 'Nina',
    rating: 1500,
    tier: 'intermediate',
    description: 'Balanced player with good positional sense',
    playStyle: 'Positional',
    emoji: '🗺️',
  },
  {
    id: 'oscar-1500',
    name: 'Oscar',
    rating: 1500,
    tier: 'intermediate',
    description: 'Tactical player who loves combinations',
    playStyle: 'Tactical',
    emoji: '⚡',
  },
  {
    id: 'priya-1600',
    name: 'Priya',
    rating: 1600,
    tier: 'intermediate',
    description: 'Precise and methodical in her approach',
    playStyle: 'Precise',
    emoji: '🎯',
  },

  // Advanced tier (1700-2000)
  {
    id: 'viktor-1700',
    name: 'Viktor',
    rating: 1700,
    tier: 'advanced',
    description: 'Aggressive attacker seeking sharp positions',
    playStyle: 'Aggressive',
    emoji: '🔥',
  },
  {
    id: 'elena-1800',
    name: 'Elena',
    rating: 1800,
    tier: 'advanced',
    description: 'Creative player with deep calculation skills',
    playStyle: 'Creative',
    emoji: '🎨',
  },
  {
    id: 'kenji-1900',
    name: 'Kenji',
    rating: 1900,
    tier: 'advanced',
    description: 'Disciplined and patient, grinds out wins',
    playStyle: 'Endgame',
    emoji: '🏁',
  },
  {
    id: 'sofia-2000',
    name: 'Sofia',
    rating: 2000,
    tier: 'advanced',
    description: 'Well-rounded expert with few weaknesses',
    playStyle: 'Universal',
    emoji: '🌐',
  },

  // Master tier (2100-2600)
  {
    id: 'magnus-2100',
    name: 'Magnus',
    rating: 2100,
    tier: 'master',
    description: 'Master-level player with exceptional endgame technique',
    playStyle: 'Technical',
    emoji: '⚙️',
  },
  {
    id: 'alexa-2300',
    name: 'Alexa',
    rating: 2300,
    tier: 'master',
    description: 'Dynamic attacker with sharp tactical vision',
    playStyle: 'Dynamic',
    emoji: '💥',
  },
  {
    id: 'kaspar-2400',
    name: 'Kaspar',
    rating: 2400,
    tier: 'master',
    description: 'Deep strategist with computer-like precision',
    playStyle: 'Strategic',
    emoji: '♟️',
  },
  {
    id: 'garuda-2600',
    name: 'Garuda',
    rating: 2600,
    tier: 'master',
    description: 'Elite grandmaster strength, unforgiving play',
    playStyle: 'Elite',
    emoji: '👑',
  },
]

export const getBotsByTier = (tier: BotTier): Bot[] => {
  return BOTS.filter((bot) => bot.tier === tier)
}

export const getBotById = (id: string): Bot | undefined => {
  return BOTS.find((bot) => bot.id === id)
}

/**
 * Resolve a bot's signature palette. Beginner heroes carry hand-picked colors;
 * every other bot gets a bright tier-default hue, cycled by its position within
 * its tier so the card layout is identical across all tiers.
 */
export const botColors = (bot: Bot): BotColors => {
  if (bot.colors) return bot.colors
  const palette = TIER_PALETTES[bot.tier]
  const idx = getBotsByTier(bot.tier).findIndex((b) => b.id === bot.id)
  return palette[(idx < 0 ? 0 : idx) % palette.length]
}
