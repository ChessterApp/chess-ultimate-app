export type BotTier = 'beginner' | 'intermediate' | 'advanced' | 'master'

export interface Bot {
  id: string
  name: string
  rating: number
  tier: BotTier
  description: string
  playStyle: string
  avatar?: string
}

export const TIER_COLORS: Record<BotTier, string> = {
  beginner: '#6B7280',
  intermediate: '#22C55E',
  advanced: '#3B82F6',
  master: '#F59E0B',
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
  },
  {
    id: 'rex-1200',
    name: 'Rex',
    rating: 1200,
    tier: 'beginner',
    description: 'Straightforward player learning the basics',
    playStyle: 'Solid',
    avatar: '/bots/rex.webp',
  },
  {
    id: 'milo-1300',
    name: 'Milo',
    rating: 1300,
    tier: 'beginner',
    description: 'Casual player who loves a good game',
    playStyle: 'Relaxed',
    avatar: '/bots/milo.webp',
  },
  {
    id: 'zara-1300',
    name: 'Zara',
    rating: 1300,
    tier: 'beginner',
    description: 'Enthusiastic learner eager to improve',
    playStyle: 'Eager',
    avatar: '/bots/zara.webp',
  },

  // Intermediate tier (1400-1600)
  {
    id: 'sven-1400',
    name: 'Sven',
    rating: 1400,
    tier: 'intermediate',
    description: 'Strategic thinker with solid fundamentals',
    playStyle: 'Strategic',
  },
  {
    id: 'nina-1500',
    name: 'Nina',
    rating: 1500,
    tier: 'intermediate',
    description: 'Balanced player with good positional sense',
    playStyle: 'Positional',
  },
  {
    id: 'oscar-1500',
    name: 'Oscar',
    rating: 1500,
    tier: 'intermediate',
    description: 'Tactical player who loves combinations',
    playStyle: 'Tactical',
  },
  {
    id: 'priya-1600',
    name: 'Priya',
    rating: 1600,
    tier: 'intermediate',
    description: 'Precise and methodical in her approach',
    playStyle: 'Precise',
  },

  // Advanced tier (1700-2000)
  {
    id: 'viktor-1700',
    name: 'Viktor',
    rating: 1700,
    tier: 'advanced',
    description: 'Aggressive attacker seeking sharp positions',
    playStyle: 'Aggressive',
  },
  {
    id: 'elena-1800',
    name: 'Elena',
    rating: 1800,
    tier: 'advanced',
    description: 'Creative player with deep calculation skills',
    playStyle: 'Creative',
  },
  {
    id: 'kenji-1900',
    name: 'Kenji',
    rating: 1900,
    tier: 'advanced',
    description: 'Disciplined and patient, grinds out wins',
    playStyle: 'Endgame',
  },
  {
    id: 'sofia-2000',
    name: 'Sofia',
    rating: 2000,
    tier: 'advanced',
    description: 'Well-rounded expert with few weaknesses',
    playStyle: 'Universal',
  },

  // Master tier (2100-2600)
  {
    id: 'magnus-2100',
    name: 'Magnus',
    rating: 2100,
    tier: 'master',
    description: 'Master-level player with exceptional endgame technique',
    playStyle: 'Technical',
  },
  {
    id: 'alexa-2300',
    name: 'Alexa',
    rating: 2300,
    tier: 'master',
    description: 'Dynamic attacker with sharp tactical vision',
    playStyle: 'Dynamic',
  },
  {
    id: 'kaspar-2400',
    name: 'Kaspar',
    rating: 2400,
    tier: 'master',
    description: 'Deep strategist with computer-like precision',
    playStyle: 'Strategic',
  },
  {
    id: 'garuda-2600',
    name: 'Garuda',
    rating: 2600,
    tier: 'master',
    description: 'Elite grandmaster strength, unforgiving play',
    playStyle: 'Elite',
  },
]

export const getBotsByTier = (tier: BotTier): Bot[] => {
  return BOTS.filter((bot) => bot.tier === tier)
}

export const getBotById = (id: string): Bot | undefined => {
  return BOTS.find((bot) => bot.id === id)
}
