import React from 'react'
import { Box, Typography } from '@mui/material'
import { useTranslations } from 'next-intl'
import BotCard from './BotCard'
import type { Bot, BotTier } from '@/data/bots'
import { getBotsByTier, tierWorld } from '@/data/bots'
import { tierLabel, worldName } from '@/lib/botI18n'
import { fredoka, nunito } from '@/lib/fonts'

interface BotGridProps {
  selectedBotId: string | null
  onSelectBot: (bot: Bot) => void
}

const TIER_ORDER: BotTier[] = ['beginner', 'intermediate', 'advanced', 'master']

export default function BotGrid({ selectedBotId, onSelectBot }: BotGridProps) {
  const t = useTranslations('bots')

  return (
    <Box>
      {TIER_ORDER.map((tier) => {
        const bots = getBotsByTier(tier)
        if (bots.length === 0) return null

        const world = tierWorld(tier)

        return (
          <Box key={tier} sx={{ mb: 5 }}>
            {/* World banner — travel to the next world as you scroll */}
            <Box
              sx={{
                mb: tier === 'beginner' ? 1.5 : 2.5,
                px: { xs: 2.5, sm: 3 },
                py: { xs: 2, sm: 2.25 },
                borderRadius: '22px',
                background: world.headerGradient,
                boxShadow: '0 10px 24px rgba(40,50,78,.16)',
              }}
            >
              <Typography
                component="h2"
                sx={{
                  fontFamily: fredoka.style.fontFamily,
                  fontWeight: 700,
                  fontSize: { xs: '26px', sm: '32px' },
                  lineHeight: 1.1,
                  color: '#fff',
                  textShadow: '0 2px 6px rgba(40,50,78,.28)',
                }}
              >
                <Box component="span" sx={{ mr: 1 }} aria-hidden="true">
                  {world.emoji}
                </Box>
                {worldName(t, tier)}
              </Typography>
              <Typography
                component="p"
                sx={{
                  mt: 0.25,
                  fontFamily: nunito.style.fontFamily,
                  fontWeight: 800,
                  fontSize: '14px',
                  letterSpacing: '0.06em',
                  textTransform: 'uppercase',
                  color: 'rgba(255,255,255,0.92)',
                }}
              >
                {tierLabel(t, tier)}
              </Typography>

              {/* Collectible subtitle (beginner heroes only) */}
              {tier === 'beginner' && (
                <Typography
                  component="p"
                  sx={{
                    mt: 1,
                    fontFamily: nunito.style.fontFamily,
                    fontWeight: 700,
                    fontSize: '16px',
                    color: '#fff',
                  }}
                >
                  {t.has('collectSubtitle')
                    ? t('collectSubtitle')
                    : 'Collect a win against every character!'}
                </Typography>
              )}
            </Box>

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
