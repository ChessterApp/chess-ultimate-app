import React from 'react'
import { Box } from '@mui/material'
import type { BotTier } from '@/data/bots'
import { tierWorld } from '@/data/bots'

interface WorldSceneryProps {
  tier: BotTier
}

/**
 * Bright, kid-friendly scenery painted behind a card's art area — one look per
 * world. Pure SVG/CSS (no image assets). Solid `fill`s (no gradient ids) so many
 * cards can render the same scenery without id collisions. Backgrounds use CSS
 * gradients on the container. `slice` makes each square art slot fully covered.
 */
export default function WorldScenery({ tier }: WorldSceneryProps) {
  const world = tierWorld(tier)
  const { primary, secondary, accent } = world.scenery

  const background: Record<BotTier, string> = {
    beginner: 'linear-gradient(180deg, #E0F2FE 0%, #7DD3FC 100%)',
    intermediate: 'linear-gradient(180deg, #D1FAE5 0%, #6EE7B7 100%)',
    advanced: 'radial-gradient(120% 90% at 50% 8%, #FFEDD5 0%, #FDBA74 45%, #FB923C 100%)',
    master: 'linear-gradient(180deg, #7C3AED 0%, #4C1D95 100%)',
  }

  return (
    <Box
      data-testid="world-scenery"
      data-tier={tier}
      aria-hidden="true"
      sx={{
        position: 'absolute',
        inset: 0,
        background: background[tier],
        pointerEvents: 'none',
      }}
    >
      <svg
        viewBox="0 0 100 100"
        preserveAspectRatio="xMidYMid slice"
        width="100%"
        height="100%"
        style={{ display: 'block' }}
      >
        {tier === 'beginner' && (
          <>
            {/* Layered river waves */}
            <path d="M0 66 Q25 58 50 66 T100 66 V100 H0 Z" fill={secondary} opacity="0.6" />
            <path d="M0 78 Q25 70 50 78 T100 78 V100 H0 Z" fill={primary} opacity="0.7" />
            <path d="M0 88 Q25 82 50 88 T100 88 V100 H0 Z" fill={accent} opacity="0.85" />
          </>
        )}

        {tier === 'intermediate' && (
          <>
            {/* Treeline silhouette */}
            <rect x="0" y="84" width="100" height="16" fill={accent} />
            <polygon points="18,84 26,58 34,84" fill={secondary} />
            <polygon points="34,84 44,50 54,84" fill={primary} />
            <polygon points="54,84 62,60 70,84" fill={secondary} />
            <polygon points="70,84 80,54 90,84" fill={primary} />
            <polygon points="2,84 10,64 18,84" fill={primary} />
          </>
        )}

        {tier === 'advanced' && (
          <>
            {/* Lava glow + volcano silhouette */}
            <circle cx="50" cy="46" r="26" fill="#FDE68A" opacity="0.55" />
            <polygon points="20,100 50,40 80,100" fill={accent} />
            {/* Lava spilling from the crater */}
            <path d="M42 46 L50 40 L58 46 L54 60 L58 74 L50 66 L44 78 L42 62 Z" fill="#FDE047" opacity="0.9" />
            <path d="M46 44 L50 40 L54 44 L52 56 L48 56 Z" fill="#FB7185" opacity="0.85" />
          </>
        )}

        {tier === 'master' && (
          <>
            {/* Stars */}
            <circle cx="18" cy="20" r="1.6" fill="#FFFFFF" />
            <circle cx="72" cy="16" r="2" fill="#FFFFFF" />
            <circle cx="40" cy="12" r="1.4" fill={accent} />
            <circle cx="86" cy="34" r="1.6" fill="#FFFFFF" />
            <circle cx="30" cy="34" r="1.4" fill={accent} />
            <circle cx="62" cy="30" r="1.8" fill="#FFFFFF" />
            {/* Drifting clouds */}
            <ellipse cx="26" cy="52" rx="18" ry="6" fill={accent} opacity="0.3" />
            <ellipse cx="78" cy="60" rx="16" ry="5" fill={accent} opacity="0.25" />
            {/* Sky castle silhouette */}
            <g fill="#5B21B6">
              <rect x="30" y="70" width="40" height="30" />
              <rect x="26" y="62" width="10" height="38" />
              <rect x="64" y="62" width="10" height="38" />
              <rect x="46" y="56" width="8" height="44" />
              {/* Battlements */}
              <rect x="26" y="60" width="3" height="4" />
              <rect x="32" y="60" width="3" height="4" />
              <rect x="65" y="60" width="3" height="4" />
              <rect x="71" y="60" width="3" height="4" />
            </g>
            {/* Castle flags */}
            <polygon points="50,50 50,56 56,53" fill={primary} />
          </>
        )}
      </svg>
    </Box>
  )
}
