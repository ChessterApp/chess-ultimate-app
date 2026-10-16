'use client';

import React, { useState } from 'react';
import { Box, ButtonBase, Tooltip, Typography } from '@mui/material';
import { MOVE_QUALITY_COLORS, canonicalNag, nagsInGroup, type NagDef } from '@/lib/nags';

export interface NagPaletteLabels {
  /** Symbol names keyed by NagDef.i18nKey */
  nagNames?: Record<string, string>;
  moreSymbols?: string;
  fewerSymbols?: string;
}

const MOVE_ROW = nagsInGroup('move');
const POSITION_ROW = nagsInGroup('position');
const OTHER_ROW = nagsInGroup('other');

function NagChip({ def, active, name, onClick }: { def: NagDef; active: boolean; name: string; onClick: () => void }) {
  const color = MOVE_QUALITY_COLORS[def.code];
  return (
    <Tooltip title={name} arrow placement="top" disableInteractive>
      <ButtonBase
        data-testid={`nag-chip-${def.code}`}
        aria-label={name}
        aria-pressed={active}
        onClick={onClick}
        sx={{
          minWidth: 26,
          height: 24,
          px: '3px',
          borderRadius: '4px',
          border: 1,
          borderColor: active ? 'transparent' : 'divider',
          bgcolor: active ? (color ?? 'primary.main') : 'transparent',
          color: active ? '#fff' : (color ?? 'text.primary'),
          fontSize: 13,
          fontWeight: 700,
          lineHeight: 1,
          '&:hover': { bgcolor: active ? (color ?? 'primary.main') : 'action.hover' },
        }}
      >
        {def.symbol}
      </ButtonBase>
    </Tooltip>
  );
}

export default function NagPalette({ nags, onToggle, labels = {} }: {
  nags: readonly number[] | undefined;
  onToggle: (code: number) => void;
  labels?: NagPaletteLabels;
}) {
  const [showMore, setShowMore] = useState(false);
  const active = new Set((nags ?? []).map(canonicalNag));
  const row = (defs: NagDef[]) => (
    <Box sx={{ display: 'flex', gap: '3px' }}>
      {defs.map(def => (
        <NagChip
          key={def.code}
          def={def}
          active={active.has(def.code)}
          name={labels.nagNames?.[def.i18nKey] ?? def.symbol}
          onClick={() => onToggle(def.code)}
        />
      ))}
    </Box>
  );

  return (
    <Box data-testid="nag-palette" sx={{ display: 'flex', flexDirection: 'column', gap: '4px', px: 1, py: 0.5 }}>
      {row(MOVE_ROW)}
      {row(POSITION_ROW)}
      {showMore && row(OTHER_ROW)}
      <ButtonBase
        onClick={() => setShowMore(v => !v)}
        aria-expanded={showMore}
        sx={{ alignSelf: 'flex-start', borderRadius: '4px', px: '4px', '&:hover': { bgcolor: 'action.hover' } }}
      >
        <Typography component="span" sx={{ fontSize: 12, color: 'primary.main' }}>
          {showMore ? labels.fewerSymbols || 'Fewer symbols' : labels.moreSymbols || 'More symbols…'}
        </Typography>
      </ButtonBase>
    </Box>
  );
}
