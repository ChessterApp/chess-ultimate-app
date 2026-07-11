import React from 'react'
import { Box, Typography } from '@mui/material'
import { useTranslations } from 'next-intl'
import BotCard from './BotCard'
import type { Bot, BotTier } from '@/data/bots'
import { getBotsByTier } from '@/data/bots'
import { tierLabel } from '@/lib/botI18n'
import { fredoka, nunito } from '@/lib/fonts'

interface BotGridProps {
  selectedBotId: string | null
  onSelectBot: (bot: Bot) => void
}

const TIER_ORDER: BotTier[] = ['beginner', 'intermediate', 'advanced', 'master']

const INK = '#28324E'
const INK_SOFT = '#5C6784'

export default function BotGrid({ selectedBotId, onSelectBot }: BotGridProps) {
  const t = useTranslations('bots')

  return (
    <Box>
      {TIER_ORDER.map((tier) => {
        const bots = getBotsByTier(tier)
        if (bots.length === 0) return null

        return (
          <Box key={tier} sx={{ mb: 5 }}>
            {/* Tier header */}
            <Typography
              component="h2"
              sx={{
                fontFamily: fredoka.style.fontFamily,
                fontWeight: 700,
                fontSize: '28px',
                color: INK,
                mb: tier === 'beginner' ? 0.5 : 2,
              }}
            >
              {tierLabel(t, tier)}
            </Typography>

            {/* Collectible subtitle (beginner heroes only) */}
            {tier === 'beginner' && (
              <Typography
                component="p"
                sx={{
                  fontFamily: nunito.style.fontFamily,
                  fontWeight: 700,
                  fontSize: '17px',
                  color: INK_SOFT,
                  mb: 2,
                }}
              >
                {t.has('collectSubtitle')
                  ? t('collectSubtitle')
                  : 'Collect a win against every character!'}
              </Typography>
            )}

            {/* Bot cards grid */}
            <Box
              sx={{
                display: 'grid',
                gridTemplateColumns: {
                  xs: '1fr',
                  sm: 'repeat(2, 1fr)',
                  md: 'repeat(4, 1fr)',
                },
                gap: '28px',
              }}
            >
              {bots.map((bot) => (
                <BotCard
                  key={bot.id}
                  bot={bot}
                  selected={selectedBotId === bot.id}
                  onClick={() => onSelectBot(bot)}
                />
              ))}
            </Box>
          </Box>
        )
      })}
    </Box>
  )
}
