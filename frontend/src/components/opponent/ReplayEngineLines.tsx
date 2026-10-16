'use client'

import { useMemo } from 'react'
import { Box } from '@mui/material'
import { formatEngineLine } from '@/lib/engine/formatEngineLine'
import EngineLineRow, { EngineLineRowSkeleton } from '@/components/engine/EngineLineRow'

interface EngineLine {
  pv: string[]       // principal variation moves in UCI format
  cp?: number        // centipawns
  mate?: number      // mate in N
  depth: number
}

interface ReplayEngineLinesProps {
  lines: EngineLine[]
  currentFen: string
  /** How many lines to show (the shared engine "Lines" setting). */
  maxLines: number
}

/**
 * Top engine lines: eval chip + up to 4 numbered full moves on one row.
 * Shows `maxLines` skeleton rows until the engine produces a line.
 */
export default function ReplayEngineLines({ lines, currentFen, maxLines }: ReplayEngineLinesProps) {
  const rows = useMemo(
    () => lines.slice(0, maxLines).map((line) => ({ ...line, tokens: formatEngineLine(currentFen, line.pv) })),
    [lines, currentFen, maxLines]
  )

  return (
    <Box data-testid="replay-engine-lines" sx={{ display: 'flex', flexDirection: 'column', minWidth: 0 }}>
      {rows.length === 0
        ? Array.from({ length: maxLines }, (_, i) => <EngineLineRowSkeleton key={i} />)
        : rows.map((line, i) => <EngineLineRow key={i} cp={line.cp} mate={line.mate} tokens={line.tokens} />)}
    </Box>
  )
}
