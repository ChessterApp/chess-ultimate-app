/**
 * GameCard — Mobile-friendly card layout for displaying a single game
 */

'use client';

import React from 'react';
import { Box, Typography, Chip, Card, CardContent } from '@mui/material';
import { useTranslations } from 'next-intl';
import type { GameSearchResult } from '@/hooks/useOpeningRepertoire';

interface GameCardProps {
  game: GameSearchResult;
  onClick?: () => void;
  showSource?: boolean;
}

export default function GameCard({ game, onClick, showSource = false }: GameCardProps) {
  const t = useTranslations('debut');

  const resultColor =
    game.result === '1-0' ? '#f0f0f0' :
    game.result === '0-1' ? '#333' :
    '#888';

  return (
    <Card
      sx={{
        bgcolor: 'rgba(255,255,255,0.03)',
        cursor: onClick ? 'pointer' : 'default',
        transition: 'all 0.15s ease',
        '&:hover': onClick ? {
          bgcolor: 'rgba(255,255,255,0.06)',
          transform: 'translateY(-1px)',
          boxShadow: '0 2px 8px rgba(0,0,0,0.3)',
        } : {},
        border: '1px solid rgba(255,255,255,0.08)',
      }}
      onClick={onClick}
    >
      <CardContent sx={{ p: 1.5, '&:last-child': { pb: 1.5 } }}>
        {/* Players */}
        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.5, mb: 1 }}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
            <Box
              sx={{
                width: 8,
                height: 8,
                bgcolor: '#f0f0f0',
                borderRadius: '50%',
                flexShrink: 0,
              }}
            />
            <Typography
              component="span"
              sx={{
                color: 'text.primary',
                fontSize: 13,
                fontWeight: 600,
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                whiteSpace: 'nowrap',
              }}
            >
              {game.white_name || game.white || '?'}
            </Typography>
            <Typography component="span" sx={{ color: 'text.secondary', fontSize: 11, flexShrink: 0 }}>
              ({game.white_elo || '?'})
            </Typography>
          </Box>

          <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
            <Box
              sx={{
                width: 8,
                height: 8,
                bgcolor: '#333',
                borderRadius: '50%',
                flexShrink: 0,
              }}
            />
            <Typography
              component="span"
              sx={{
                color: 'text.primary',
                fontSize: 13,
                fontWeight: 600,
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                whiteSpace: 'nowrap',
              }}
            >
              {game.black_name || game.black || '?'}
            </Typography>
            <Typography component="span" sx={{ color: 'text.secondary', fontSize: 11, flexShrink: 0 }}>
              ({game.black_elo || '?'})
            </Typography>
          </Box>
        </Box>

        {/* Meta info */}
        <Box sx={{ display: 'flex', gap: 0.5, flexWrap: 'wrap', alignItems: 'center' }}>
          <Chip
            label={game.result || '?'}
            size="small"
            sx={{
              height: 18,
              fontSize: 10,
              bgcolor: resultColor,
              color: game.result === '0-1' ? '#fff' : '#000',
              fontWeight: 600,
            }}
          />
          {game.eco && (
            <Chip
              label={game.eco}
              size="small"
              sx={{ height: 18, fontSize: 9, bgcolor: '#1f2937', color: '#fff' }}
            />
          )}
          {game.event && (
            <Chip
              label={game.event}
              size="small"
              sx={{ height: 18, fontSize: 9, bgcolor: 'action.hover', color: 'text.secondary' }}
            />
          )}
          {(game.date || game.year) && (
            <Typography component="span" sx={{ color: 'text.secondary', fontSize: 10, ml: 'auto' }}>
              {game.date || game.year}
            </Typography>
          )}
          {showSource && game.source && (
            <Chip
              label={game.source}
              size="small"
              sx={{
                height: 16,
                fontSize: 8,
                bgcolor: '#14b8a6',
                color: '#fff',
                textTransform: 'uppercase',
                fontWeight: 700,
              }}
            />
          )}
        </Box>

        {/* Opening name if available */}
        {game.opening && (
          <Typography
            variant="caption"
            sx={{
              color: 'text.secondary',
              fontSize: 10,
              fontStyle: 'italic',
              display: 'block',
              mt: 0.5,
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
            }}
          >
            {game.opening}
          </Typography>
        )}
      </CardContent>
    </Card>
  );
}
