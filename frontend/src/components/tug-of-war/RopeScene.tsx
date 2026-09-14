/**
 * RopeScene — the tug animation (LOCKED mechanic).
 *
 * One looping scene (both pullers + rope baked in) slides horizontally past a
 * fixed center line as the rope differential changes; a single translateX with
 * a framer-motion spring makes each score change read as a yank. On win the
 * scene is swapped for the winning side's celebration clip with a scale bump.
 *
 * Asset mapping (verify visually, swap if wrong): red = LEFT / Team A, blue =
 * RIGHT / Team B.
 */

'use client';

import { motion } from 'framer-motion';
import type { TeamSide } from '@/lib/tug-of-war/types';

/** Percent of scene width shifted per rope step. |5| * K drags well past center. */
const K = 8;

interface RopeSceneProps {
  /** Rope differential, −5..+5 (positive = Team A / left ahead). */
  rope: number;
  /** Set once the match is over. */
  winner: TeamSide | null;
}

export default function RopeScene({ rope, winner }: RopeSceneProps) {
  // Positive rope favours Team A (left), so the scene slides left.
  const offset = -rope * K;
  const src = winner
    ? winner === 'A'
      ? '/tug-of-war/win-red.gif'
      : '/tug-of-war/win-blue.gif'
    : '/tug-of-war/pull-loop.gif';

  return (
    <div className="relative w-full overflow-hidden rounded-2xl bg-slate-900/60 border border-white/10">
      {/* Fixed center win-threshold line — never moves. */}
      <div className="pointer-events-none absolute left-1/2 top-0 bottom-0 z-10 w-[2px] -translate-x-1/2 bg-white/70" />
      <div className="flex items-center justify-center py-3">
        <motion.img
          key={src}
          src={src}
          alt=""
          aria-hidden="true"
          draggable={false}
          className="h-[clamp(120px,22vh,240px)] w-auto max-w-none select-none"
          animate={{ x: `${winner ? 0 : offset}%`, scale: winner ? 1.06 : 1 }}
          transition={
            winner
              ? { type: 'spring', stiffness: 180, damping: 12 }
              : { type: 'spring', stiffness: 220, damping: 14, mass: 0.9 }
          }
        />
      </div>
    </div>
  );
}
