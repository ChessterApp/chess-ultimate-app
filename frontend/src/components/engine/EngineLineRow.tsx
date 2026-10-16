'use client';

import { Box, Skeleton, Typography } from '@mui/material';
import type { EngineLineToken } from '@/lib/engine/formatEngineLine';

interface EngineLineRowProps {
  cp?: number;
  mate?: number;
  tokens: EngineLineToken[];
  /** Win probability (0–100) for the side the eval refers to, shown under the eval. */
  winPercent?: number;
  onClick?: () => void;
}

export function formatEval(cp?: number, mate?: number): string {
  if (mate !== undefined) return mate < 0 ? `-M${Math.abs(mate)}` : `M${mate}`;
  if (cp === undefined) return '0.00';
  const pawns = cp / 100;
  return pawns >= 0 ? `+${pawns.toFixed(2)}` : pawns.toFixed(2);
}

function evalColor(cp?: number, mate?: number): string {
  if (mate !== undefined) return mate < 0 ? 'error.main' : 'success.main';
  if (cp !== undefined && cp > 100) return 'success.main';
  if (cp !== undefined && cp < -100) return 'error.main';
  return 'text.secondary';
}

const ROW_SX = {
  display: 'flex',
  alignItems: 'center',
  gap: 1,
  px: 1,
  py: 0.5,
  borderRadius: 1,
  minWidth: 0,
} as const;

const MOVES_SX = {
  flex: 1,
  minWidth: 0,
  whiteSpace: 'nowrap',
  overflow: 'hidden',
  fontSize: '11.5px',
  '@media (min-width: 400px)': { fontSize: '12.5px' },
} as const;

/** One engine line: eval chip + numbered PV on a single, non-wrapping row. */
export default function EngineLineRow({ cp, mate, tokens, winPercent, onClick }: EngineLineRowProps) {
  return (
    <Box
      sx={{ ...ROW_SX, cursor: onClick ? 'pointer' : 'default', '&:hover': onClick ? { bgcolor: 'action.hover' } : undefined }}
      onClick={onClick}
      role={onClick ? 'button' : undefined}
      data-testid="engine-line-row"
    >
      <Box sx={{ flexShrink: 0, minWidth: 48, textAlign: 'right', lineHeight: 1.1 }}>
        <Typography
          component="span"
          sx={{ fontFamily: 'monospace', fontWeight: 600, fontSize: '12.5px', color: evalColor(cp, mate) }}
        >
          {formatEval(cp, mate)}
        </Typography>
        {winPercent !== undefined && (
          <Typography component="div" color="text.secondary" sx={{ fontSize: '10px' }}>
            {Math.round(winPercent)}%
          </Typography>
        )}
      </Box>
      <Typography component="div" sx={MOVES_SX} data-testid="engine-line-moves">
        {tokens.map((token, i) => (
          <span key={i}>
            {i > 0 && ' '}
            {token.num && (
              <Box component="span" sx={{ color: 'text.secondary' }}>
                {token.num}
              </Box>
            )}
            <Box component="span" sx={i === 0 ? { fontWeight: 600 } : undefined}>
              {token.san}
            </Box>
          </span>
        ))}
      </Typography>
    </Box>
  );
}

/** Placeholder row shown while the engine has not produced a line yet. */
export function EngineLineRowSkeleton() {
  return (
    <Box sx={ROW_SX} data-testid="engine-line-skeleton">
      <Skeleton variant="rounded" width={48} height={16} />
      <Skeleton variant="text" sx={{ flex: 1, fontSize: '12.5px' }} />
    </Box>
  );
}
