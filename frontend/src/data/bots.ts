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

/**
 * Each tier is a bright, kid-friendly "world" the player travels through as
 * they climb the ladder. World colors compose with {@link botColors}: the frame
 * (border/tint) themes every card in the tier, while beginner heroes keep their
 * personal signature colors on the name banner so the four stay distinct.
 */
export interface TierWorld {
  /** i18n key under `bots.worlds.*`. */
  key: string
  /** Emoji shown before the world name in the section banner. */
  emoji: string
  /** Scenery colors painted into the card art backdrop (SVG/CSS, no images). */
  scenery: { primary: string; secondary: string; accent: string }
  /** CSS gradient for the section banner. */
  headerGradient: string
  /** Full-screen 160deg world gradient dipping the in-game play screen. */
  screenGradient: string
  /** Three low-opacity scenery emojis floated around the in-game screen. */
  deco: [string, string, string]
  /** Card frame palette (border + background tint) applied across the tier. */
  frame: BotColors
}

export const TIER_WORLDS: Record<BotTier, TierWorld> = {
  beginner: {
    key: 'freshRiver',
    emoji: '🌊',
    scenery: { primary: '#38BDF8', secondary: '#7DD3FC', accent: '#0EA5E9' },
    headerGradient: 'linear-gradient(135deg, #38BDF8 0%, #22D3EE 100%)',
    screenGradient: 'linear-gradient(160deg, #38BDF8 0%, #22D3EE 55%, #7DD3FC 100%)',
    deco: ['🌊', '🐟', '🫧'],
    frame: { main: '#38BDF8', deep: '#0369A1', tint: '#EAF7FF' },
  },
  intermediate: {
    key: 'emeraldForest',
    emoji: '🌲',
    scenery: { primary: '#34D399', secondary: '#10B981', accent: '#047857' },
    headerGradient: 'linear-gradient(135deg, #10B981 0%, #34D399 100%)',
    screenGradient: 'linear-gradient(160deg, #10B981 0%, #34D399 55%, #6EE7B7 100%)',
    deco: ['🌲', '🍄', '🦋'],
    frame: { main: '#10B981', deep: '#047857', tint: '#ECFDF5' },
  },
  advanced: {
    key: 'volcanoArena',
    emoji: '🌋',
    scenery: { primary: '#FB923C', secondary: '#F97316', accent: '#EF4444' },
    headerGradient: 'linear-gradient(135deg, #F97316 0%, #EF4444 100%)',
    screenGradient: 'linear-gradient(160deg, #F97316 0%, #EF4444 55%, #FCA5A5 100%)',
    deco: ['🌋', '🔥', '⚡'],
    frame: { main: '#F97316', deep: '#C2410C', tint: '#FFF3E9' },
  },
  master: {
    key: 'skyCastle',
    emoji: '🏰',
    scenery: { primary: '#6D28D9', secondary: '#4C1D95', accent: '#C4B5FD' },
    headerGradient: 'linear-gradient(135deg, #6D28D9 0%, #9333EA 100%)',
    screenGradient: 'linear-gradient(160deg, #6D28D9 0%, #9333EA 55%, #C4B5FD 100%)',
    deco: ['🏰', '☁️', '⭐'],
    frame: { main: '#8B5CF6', deep: '#6D28D9', tint: '#F5F1FF' },
  },
}

/** The world config for a tier. */
export const tierWorld = (tier: BotTier): TierWorld => TIER_WORLDS[tier]

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
    avatar: '/bots/sven.webp',
    emoji: '🧠',
  },
  {
    id: 'nina-1500',
    name: 'Nina',
    rating: 1500,
    tier: 'intermediate',
    description: 'Balanced player with good positional sense',
    playStyle: 'Positional',
    avatar: '/bots/nina.webp',
    emoji: '🗺️',
  },
  {
    id: 'oscar-1500',
    name: 'Oscar',
    rating: 1500,
    tier: 'intermediate',
    description: 'Tactical player who loves combinations',
    playStyle: 'Tactical',
    avatar: '/bots/oscar.webp',
    emoji: '⚡',
  },
  {
    id: 'kristy-1600',
    name: 'Kristy',
    rating: 1600,
    tier: 'intermediate',
    description: 'Precise and methodical in her approach',
    playStyle: 'Precise',
    avatar: '/bots/kristy.webp',
    emoji: '🎯',
  },

  // Advanced tier (1700-2000)
  {
    id: 'viktor-1700',
    name: 'Kai',
    rating: 1700,
    tier: 'advanced',
    description: 'Aggressive attacker seeking sharp positions',
    playStyle: 'Aggressive',
    avatar: '/bots/kai.webp',
    emoji: '🔥',
  },
  {
    id: 'elena-1800',
    name: 'Blaze',
    rating: 1800,
    tier: 'advanced',
    description: 'Creative player with deep calculation skills',
    playStyle: 'Creative',
    avatar: '/bots/blaze.webp',
    emoji: '🎨',
  },
  {
    id: 'kenji-1900',
    name: 'Vulcan',
    rating: 1900,
    tier: 'advanced',
    description: 'Disciplined and patient, grinds out wins',
    playStyle: 'Endgame',
    avatar: '/bots/vulcan.webp',
    emoji: '🏁',
  },
  {
    id: 'sofia-2000',
    name: 'Ember',
    rating: 2000,
    tier: 'advanced',
    description: 'Well-rounded expert with few weaknesses',
    playStyle: 'Universal',
    avatar: '/bots/ember.webp',
    emoji: '🌐',
  },

  // Master tier (2100-2600)
  {
    id: 'magnus-2100',
    name: 'Capa',
    rating: 2100,
    tier: 'master',
    description: 'Master-level player with exceptional endgame technique',
    playStyle: 'Technical',
    avatar: '/bots/magnus.webp',
    emoji: '⚙️',
  },
  {
    id: 'alexa-2300',
    name: 'Magician',
    rating: 2300,
    tier: 'master',
    description: 'Dynamic attacker with sharp tactical vision',
    playStyle: 'Dynamic',
    avatar: '/bots/alexa.webp',
    emoji: '💥',
  },
  {
    id: 'kaspar-2400',
    name: 'Kaspar',
    rating: 2400,
    tier: 'master',
    description: 'Deep strategist with computer-like precision',
    playStyle: 'Strategic',
    avatar: '/bots/kaspar.webp',
    emoji: '♟️',
  },
  {
    id: 'garuda-2600',
    name: 'Magnus',
    rating: 2600,
    tier: 'master',
    description: 'Elite grandmaster strength, unforgiving play',
    playStyle: 'Elite',
    avatar: '/bots/garuda.webp',
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

/** Resolved theme for the V3 "Immersive World" in-game play screen. */
export interface GameTheme {
  /** Full-screen world gradient behind the whole in-game view. */
  screenGradient: string
  /** Three low-opacity scenery emojis floated around the screen. */
  deco: [string, string, string]
  /** World emoji + i18n key for the "world" ghost pill. */
  worldEmoji: string
  worldKey: string
  /** Accent colors (border/disc/button shadow). */
  main: string
  /** Deep shade for bubble text, avatar shadow, soft shadows. */
  deep: string
  /** Soft tint for disc/thinking-bubble backgrounds. */
  tint: string
}

/**
 * Theme for the in-game screen: the tier's world gradient dips the whole screen,
 * while accent colors come from the bot's personal palette (beginner heroes) or
 * the tier frame (everyone else). Keeps play-screen components free of hardcoded
 * hex values.
 */
export const gameTheme = (bot: Bot): GameTheme => {
  const world = tierWorld(bot.tier)
  const accent = bot.colors ?? world.frame
  return {
    screenGradient: world.screenGradient,
    deco: world.deco,
    worldEmoji: world.emoji,
    worldKey: world.key,
    main: accent.main,
    deep: accent.deep,
    tint: accent.tint,
  }
}
