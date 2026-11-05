'use client';

import React, { useState } from 'react';
import { Box, ButtonBase, Typography } from '@mui/material';
import { useTranslations } from 'next-intl';
import type { ForkOption } from '@/lib/variationFork';

/** Rows shown before the "+N more" expander. */
const COLLAPSED_ROWS = 3;

interface VariationForkPickerProps {
  options: ForkOption[];
  /** 1-based index of the highlighted option (what Next plays). */
  highlightedIndex: number;
  /** Side to move at the fork. */
  turn: 'white' | 'black';
  onSelect: (nodeId: string) => void;
}

const MONO = 'monospace';

/**
 * Line preview list shown at a variation fork: one row per continuation with
 * the move, where the line leads and how long it is. Tapping a row enters it.
 */
export default function VariationForkPicker({ options, highlightedIndex, turn, onSelect }: VariationForkPickerProps) {
  const t = useTranslations('debut.myGames.fork');
  const [expanded, setExpanded] = useState(false);
  if (options.length < 2) return null;

  // A highlight beyond the collapsed rows (keys 4–9) must stay visible.
  const showAll = expanded || highlightedIndex > COLLAPSED_ROWS;
  const visible = showAll ? options : options.slice(0, COLLAPSED_ROWS);
  const hidden = options.length - visible.length;
  const header = t(turn === 'white' ? 'whiteContinuations' : 'blackContinuations', { count: options.length });

  return (
    <Box
      role="group"
      aria-label={header}
      data-testid="fork-picker"
      sx={{
        bgcolor: 'var(--surface-card)',
        border: '1px solid var(--border-default)',
        borderRadius: '10px',
        p: { xs: 0.75, sm: 1 },
        mb: 1,
      }}
    >
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', px: 0.5, pb: 0.75 }}>
        <Typography component="span" sx={{ fontSize: 11, fontWeight: 600, letterSpacing: '0.04em', textTransform: 'uppercase', color: 'var(--text-secondary)' }}>
          ⑂ {header}
        </Typography>
        <Typography component="span" sx={{ display: { xs: 'none', md: 'inline' }, fontSize: 11, fontWeight: 500, color: 'var(--text-tertiary)' }}>
          {t('keysHint', { count: Math.min(options.length, 9) })}
        </Typography>
      </Box>

      {visible.map(option => {
        const active = option.index === highlightedIndex;
        return (
          <ButtonBase
            key={option.nodeId}
            onClick={() => onSelect(option.nodeId)}
            aria-label={t('option', { index: option.index, move: option.moveLabel })}
            aria-current={active ? 'true' : undefined}
            data-testid={`fork-option-${option.index}`}
            sx={{
              width: '100%',
              display: 'flex',
              alignItems: 'center',
              gap: 1.25,
              textAlign: 'left',
              px: 1,
              py: { xs: 0.75, sm: 1 },
              mb: 0.5,
              borderRadius: '8px',
              border: '1.5px solid',
              borderColor: active ? option.color : 'transparent',
              bgcolor: active ? `${option.color}14` : 'var(--surface-card-hover)',
              transition: 'background-color 0.15s, border-color 0.15s',
              '&:hover': { borderColor: active ? option.color : 'var(--border-strong)' },
              '&.Mui-focusVisible': { outline: '2px solid var(--border-focus)', outlineOffset: 1 },
            }}
          >
            <Box
              component="span"
              aria-hidden
              sx={{
                flex: 'none', width: 18, height: 18, borderRadius: '9px', bgcolor: option.color, color: '#fff',
                fontSize: 11, fontWeight: 700, display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
              }}
            >
              {option.index}
            </Box>
            <Box sx={{ minWidth: 0, flex: 1 }}>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75 }}>
                <Typography component="span" sx={{ fontFamily: MONO, fontSize: 13.5, fontWeight: 700, color: 'var(--text-primary)', whiteSpace: 'nowrap' }}>
                  {option.moveLabel}
                </Typography>
                {option.isMain && (
                  <Typography
                    component="span"
                    sx={{
                      fontSize: 9.5, fontWeight: 700, textTransform: 'uppercase', borderRadius: '4px', px: '5px', py: '1px',
                      bgcolor: 'var(--accent-green-bg)', color: 'var(--accent-green-text)',
                    }}
                  >
                    {t('main')}
                  </Typography>
                )}
              </Box>
              {option.previewSan && (
                <Typography
                  component="span"
                  sx={{
                    display: 'block', fontFamily: MONO, fontSize: 11.5, color: 'var(--text-secondary)',
                    whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
                  }}
                >
                  {option.previewSan}
                </Typography>
              )}
            </Box>
            <Typography component="span" sx={{ flex: 'none', fontSize: 11, color: 'var(--text-tertiary)', whiteSpace: 'nowrap' }}>
              {t('moves', { count: option.lineLength })} ›
            </Typography>
          </ButtonBase>
        );
      })}

      {hidden > 0 && (
        <ButtonBase
          onClick={() => setExpanded(true)}
          data-testid="fork-more"
          sx={{
            width: '100%', justifyContent: 'flex-start', px: 1, py: 0.75, borderRadius: '8px',
            fontSize: 12, fontWeight: 600, color: 'var(--text-secondary)',
            '&:hover': { bgcolor: 'var(--surface-card-hover)' },
            '&.Mui-focusVisible': { outline: '2px solid var(--border-focus)', outlineOffset: 1 },
          }}
        >
          {t('more', { count: hidden })}
        </ButtonBase>
      )}
    </Box>
  );
}
