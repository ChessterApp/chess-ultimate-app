/**
 * ArenaRope — the scoreboard rope track for the bot-mode Arena: a twisted
 * rope with one tick per rope step (−ROPE_LIMIT..+ROPE_LIMIT), blue end
 * marker left (you), red end marker right (the zebra), and a knot that springs
 * to the current rope value and jerks on every pull.
 */

'use client';

import type { Ref } from 'react';
import { motion, useReducedMotion } from 'framer-motion';
import { ROPE_LIMIT } from '@/lib/tug-of-war/gameReducer';

/** Left offset (%) of a rope value: positive = toward the player (left). */
export function ropePercent(rope: number): number {
  return 50 - (rope / ROPE_LIMIT) * 50;
}

const STEPS = Array.from({ length: 2 * ROPE_LIMIT + 1 }, (_, i) => i - ROPE_LIMIT);

interface ArenaRopeProps {
  /** Rope differential, −ROPE_LIMIT..+ROPE_LIMIT (positive = player ahead). */
  rope: number;
  /** Bumps on every solve so the knot jerks even when clamped at an end. */
  pulls: number;
  knotRef?: Ref<HTMLDivElement>;
}

export default function ArenaRope({ rope, pulls, knotRef }: ArenaRopeProps) {
  const reduce = useReducedMotion();
  const leader = rope > 0 ? 'bg-blue-500' : rope < 0 ? 'bg-red-500' : 'bg-white/70';
  return (
    <div className="relative h-[5.5vh] w-full" data-testid="tug-arena-rope">
      {STEPS.map((step) => (
        <span
          key={step}
          data-testid="tug-rope-tick"
          aria-hidden="true"
          className={`absolute top-0 w-[2px] -translate-x-1/2 rounded-full ${
            step === -ROPE_LIMIT
              ? 'h-[2.6vh] w-[4px] bg-red-500'
              : step === ROPE_LIMIT
                ? 'h-[2.6vh] w-[4px] bg-blue-500'
                : step === 0
                  ? 'h-[2.2vh] bg-white/60'
                  : 'h-[1.3vh] bg-white/25'
          }`}
          style={{ left: `${ropePercent(step)}%` }}
        />
      ))}
      {/* Twisted rope */}
      <div
        aria-hidden="true"
        className="absolute inset-x-0 top-[3vh] h-[1.3vh] rounded-full shadow-[inset_0_-2px_3px_rgba(0,0,0,0.35)]"
        style={{
          background:
            'repeating-linear-gradient(115deg, #d9b26f 0 6px, #a87a3d 6px 10px), linear-gradient(#e7c98f, #8a6430)',
          backgroundBlendMode: 'multiply',
        }}
      />
      <motion.div
        ref={knotRef}
        data-testid="tug-rope-knot"
        data-rope={rope}
        className="absolute top-[3.65vh] z-10 -translate-x-1/2 -translate-y-1/2"
        initial={false}
        animate={{ left: `${ropePercent(rope)}%` }}
        transition={reduce ? { duration: 0 } : { type: 'spring', stiffness: 260, damping: 13, mass: 0.8 }}
      >
        <motion.div
          key={pulls}
          className={`flex h-[3.2vh] w-[3.2vh] items-center justify-center rounded-full border-[3px] border-white shadow-[0_0_14px_rgba(0,0,0,0.6)] ${leader}`}
          initial={reduce ? false : { scale: 1.45, rotate: -12 }}
          animate={{ scale: 1, rotate: 0 }}
          transition={{ type: 'spring', stiffness: 420, damping: 10 }}
        >
          <span className="h-[1vh] w-[1vh] rounded-full bg-white" />
        </motion.div>
      </motion.div>
    </div>
  );
}
