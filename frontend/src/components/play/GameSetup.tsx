import React from 'react'
import { Box, Button, Typography, Avatar, Chip, Paper, ButtonGroup } from '@mui/material'
import type { Bot } from '@/data/bots'
import { TIER_COLORS } from '@/data/bots'

type PlayerColor = 'white' | 'black' | 'random'

interface GameSetupProps {
  bot: Bot
  playerColor: PlayerColor
  onColorChange: (color: PlayerColor) => void
  onPlay: () => void
  onChangeBot: () => void
  disabled?: boolean
}

export default function GameSetup({
  bot,
  playerColor,
  onColorChange,
  onPlay,
  onChangeBot,
  disabled = false,
}: GameSetupProps) {
  const tierColor = TIER_COLORS[bot.tier]

  return (
    <Paper sx={{ p: 4, maxWidth: 600, mx: 'auto' }}>
      {/* Selected bot mini-card */}
      <Box
        sx={{
          display: 'flex',
          alignItems: 'center',
          gap: 2,
          mb: 3,
          p: 2,
          bgcolor: '#0f0f0f',
          borderRadius: 1,
          border: `1px solid ${tierColor}40`,
        }}
      >
        <Avatar
          sx={{
            width: 56,
            height: 56,
            bgcolor: tierColor,
            fontSize: '1.5rem',
            fontWeight: 'bold',
            color: '#fff',
          }}
        >
          {bot.name[0]}
        </Avatar>

        <Box sx={{ flex: 1 }}>
          <Typography variant="h6" sx={{ fontWeight: 'bold' }}>
            {bot.name}
          </Typography>
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

        <Button
          variant="text"
          size="small"
          onClick={onChangeBot}
          sx={{ color: tierColor, textTransform: 'none' }}
        >
          Change Bot
        </Button>
      </Box>

      {/* Color choice */}
      <Box sx={{ mb: 4 }}>
        <Typography variant="subtitle2" sx={{ mb: 1.5, fontWeight: 'bold' }}>
          Play as
        </Typography>
        <ButtonGroup fullWidth size="large">
          <Button
            variant={playerColor === 'white' ? 'contained' : 'outlined'}
            onClick={() => onColorChange('white')}
            sx={{
              py: 1.5,
              fontWeight: playerColor === 'white' ? 'bold' : 'normal',
            }}
          >
            White
          </Button>
          <Button
            variant={playerColor === 'random' ? 'contained' : 'outlined'}
            onClick={() => onColorChange('random')}
            sx={{
              py: 1.5,
              fontWeight: playerColor === 'random' ? 'bold' : 'normal',
            }}
          >
            Random
          </Button>
          <Button
            variant={playerColor === 'black' ? 'contained' : 'outlined'}
            onClick={() => onColorChange('black')}
            sx={{
              py: 1.5,
              fontWeight: playerColor === 'black' ? 'bold' : 'normal',
            }}
          >
            Black
          </Button>
        </ButtonGroup>
      </Box>

      {/* Play button */}
      <Button
        variant="contained"
        color="success"
        fullWidth
        size="large"
        onClick={onPlay}
        disabled={disabled}
        sx={{
          py: 2,
          fontSize: '1.125rem',
          fontWeight: 'bold',
          textTransform: 'none',
          bgcolor: '#22C55E',
          '&:hover': {
            bgcolor: '#16A34A',
          },
        }}
      >
        Play
      </Button>
    </Paper>
  )
}
