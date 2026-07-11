import React from 'react'
import { Box, Button, Typography, Avatar, Paper, ButtonGroup } from '@mui/material'
import { useTranslations } from 'next-intl'
import type { Bot } from '@/data/bots'
import { botColors } from '@/data/bots'
import { botDescription } from '@/lib/botI18n'
import { fredoka, nunito } from '@/lib/fonts'

type PlayerColor = 'white' | 'black' | 'random'

interface GameSetupProps {
  bot: Bot
  playerColor: PlayerColor
  onColorChange: (color: PlayerColor) => void
  onPlay: () => void
  onChangeBot: () => void
  disabled?: boolean
}

const INK = '#28324E'
const INK_SOFT = '#5C6784'
const GOLD = '#FFC53D'
const GOLD_TEXT = '#6B4A00'

export default function GameSetup({
  bot,
  playerColor,
  onColorChange,
  onPlay,
  onChangeBot,
  disabled = false,
}: GameSetupProps) {
  const t = useTranslations('bots')
  const { main, deep, tint } = botColors(bot)

  return (
    <Paper
      sx={{
        p: 4,
        maxWidth: 600,
        mx: 'auto',
        bgcolor: '#F3F7FF',
        borderRadius: '24px',
      }}
    >
      {/* Selected bot mini-card */}
      <Box
        sx={{
          display: 'flex',
          alignItems: 'center',
          gap: 2,
          mb: 3,
          p: 2,
          bgcolor: tint,
          borderRadius: '20px',
          border: `3px solid ${main}`,
        }}
      >
        <Avatar
          src={bot.avatar}
          alt={bot.name}
          sx={{
            width: 80,
            height: 80,
            bgcolor: tint,
            border: `3px solid ${main}`,
            fontFamily: fredoka.style.fontFamily,
            fontSize: '2rem',
            fontWeight: 700,
            color: deep,
          }}
        >
          {bot.name[0]}
        </Avatar>

        <Box sx={{ flex: 1, minWidth: 0 }}>
          <Typography
            component="div"
            sx={{
              fontFamily: fredoka.style.fontFamily,
              fontWeight: 700,
              fontSize: '24px',
              color: INK,
              lineHeight: 1.15,
            }}
          >
            {bot.name}
          </Typography>
          <Box
            component="span"
            sx={{
              display: 'inline-block',
              mt: 0.5,
              bgcolor: GOLD,
              color: GOLD_TEXT,
              fontFamily: nunito.style.fontFamily,
              fontWeight: 800,
              fontSize: '13px',
              borderRadius: '999px',
              px: '10px',
              py: '3px',
            }}
          >
            ⭐ {bot.rating}
          </Box>
          <Typography
            component="p"
            sx={{
              mt: 0.75,
              fontFamily: nunito.style.fontFamily,
              fontWeight: 700,
              fontSize: '14px',
              color: INK_SOFT,
              lineHeight: 1.4,
            }}
          >
            {botDescription(t, bot)}
          </Typography>
        </Box>

        <Button
          variant="text"
          size="small"
          onClick={onChangeBot}
          sx={{
            color: deep,
            fontFamily: nunito.style.fontFamily,
            fontWeight: 800,
            textTransform: 'none',
            alignSelf: 'flex-start',
          }}
        >
          Change Bot
        </Button>
      </Box>

      {/* Color choice */}
      <Box sx={{ mb: 4 }}>
        <Typography
          component="div"
          sx={{
            mb: 1.5,
            fontFamily: fredoka.style.fontFamily,
            fontWeight: 600,
            fontSize: '16px',
            color: INK,
          }}
        >
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
