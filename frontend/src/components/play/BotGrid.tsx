import React from 'react'
import { Box, Typography } from '@mui/material'
import BotCard from './BotCard'
import type { Bot, BotTier } from '@/data/bots'
import { BOTS, TIER_LABELS, getBotsByTier } from '@/data/bots'

interface BotGridProps {
  selectedBotId: string | null
  onSelectBot: (bot: Bot) => void
}

const TIER_ORDER: BotTier[] = ['beginner', 'intermediate', 'advanced', 'master']

export default function BotGrid({ selectedBotId, onSelectBot }: BotGridProps) {
  return (
    <Box>
      {TIER_ORDER.map((tier) => {
        const bots = getBotsByTier(tier)
        if (bots.length === 0) return null

        return (
          <Box key={tier} sx={{ mb: 4 }}>
            {/* Tier header */}
            <Typography
              variant="h6"
              sx={{
                mb: 2,
                fontWeight: 'bold',
                color: 'text.primary',
              }}
            >
              {TIER_LABELS[tier]}
            </Typography>

            {/* Bot cards grid */}
            <Box
              sx={{
                display: 'grid',
                gridTemplateColumns: {
                  xs: '1fr',
                  sm: 'repeat(2, 1fr)',
                  md: 'repeat(4, 1fr)',
                },
                gap: 2,
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
