import React from 'react'
import { Card, CardContent, Box, Typography, Chip, Avatar } from '@mui/material'
import type { Bot } from '@/data/bots'
import { TIER_COLORS } from '@/data/bots'

interface BotCardProps {
  bot: Bot
  selected?: boolean
  onClick: () => void
}

export default function BotCard({ bot, selected = false, onClick }: BotCardProps) {
  const tierColor = TIER_COLORS[bot.tier]

  return (
    <Card
      onClick={onClick}
      sx={{
        cursor: 'pointer',
        position: 'relative',
        transition: 'all 0.2s ease',
        border: selected ? `2px solid ${tierColor}` : '2px solid transparent',
        boxShadow: selected ? `0 0 12px ${tierColor}40` : undefined,
        '&:hover': {
          transform: 'scale(1.02)',
          boxShadow: `0 4px 12px rgba(0,0,0,0.3)`,
        },
        bgcolor: '#1a1a1a',
      }}
    >
      <CardContent sx={{ p: 2.5 }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, mb: 1.5 }}>
          {/* Avatar with initials */}
          <Avatar
            sx={{
              width: 48,
              height: 48,
              bgcolor: tierColor,
              fontSize: '1.25rem',
              fontWeight: 'bold',
              color: '#fff',
            }}
          >
            {bot.name[0]}
          </Avatar>

          <Box sx={{ flex: 1 }}>
            {/* Bot name */}
            <Typography variant="h6" sx={{ fontWeight: 'bold', lineHeight: 1.2 }}>
              {bot.name}
            </Typography>

            {/* Rating badge */}
            <Chip
              label={bot.rating}
              size="small"
              sx={{
                mt: 0.5,
                height: 20,
                fontSize: '0.75rem',
                fontWeight: 'bold',
                bgcolor: tierColor,
                color: '#fff',
              }}
            />
          </Box>
        </Box>

        {/* Description */}
        <Typography
          variant="body2"
          color="text.secondary"
          sx={{ mb: 1, fontSize: '0.875rem', lineHeight: 1.4 }}
        >
          {bot.description}
        </Typography>

        {/* Play style tag */}
        <Chip
          label={bot.playStyle}
          size="small"
          variant="outlined"
          sx={{
            height: 24,
            fontSize: '0.75rem',
            borderColor: tierColor,
            color: tierColor,
          }}
        />
      </CardContent>
    </Card>
  )
}
