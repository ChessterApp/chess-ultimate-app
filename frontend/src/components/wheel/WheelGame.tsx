'use client';

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import Link from 'next/link';
import { useTranslations } from 'next-intl';
import { pickIndex, randomUnit } from '@/lib/wheel/random';
import { winnerAngleRad } from '@/lib/wheel/physics';
import { prefersReducedMotion } from '@/lib/chess/animations';
import { isSpinnable } from '@/lib/wheel/presets';
import type { WheelSegment } from '@/lib/wheel/types';
import Wheel from './Wheel';
import WinnerModal from './WinnerModal';
import ConfigEditor from './ConfigEditor';
import { usePresets } from './usePresets';
import { useTickSound } from './useTickSound';
import { useWheelPhysics } from './useWheelPhysics';
import { fireConfetti } from './confetti';

// Fraction of a slice width the landing is randomly offset from dead-center, so
// the wheel doesn't always stop on the exact bisector.
const JITTER_SPAN = 0.7;

function vibrate(pattern: number | number[]): void {
  if (typeof navigator !== 'undefined' && typeof navigator.vibrate === 'function') {
    try {
      navigator.vibrate(pattern);
    } catch {
      /* ignore */
    }
  }
}

export default function WheelGame() {
  const t = useTranslations('wheel');
  const presetsApi = usePresets();
  const { current } = presetsApi;
  const { ensureCtx, tick } = useTickSound();

  const [winner, setWinner] = useState<WheelSegment | null>(null);
  const [editing, setEditing] = useState(false);

  const segments = useMemo(() => current?.segments ?? [], [current]);
  const count = segments.length;

  // The winner is chosen up-front but only revealed when the physics engine
  // reports it has entered the Stopped phase (no setTimeout).
  const pendingWinner = useRef<WheelSegment | null>(null);

  const { discRef, spin: startSpin, startIdle, isSpinning } = useWheelPhysics({
    onCrossing: tick,
    onStopped: () => {
      const w = pendingWinner.current;
      if (!w) return;
      setWinner(w);
      fireConfetti();
      vibrate([60, 40, 120]);
    },
  });

  const canSpin = isSpinnable(current) && !isSpinning;

  const spin = useCallback(() => {
    if (!isSpinnable(current) || isSpinning || count < 2) return;

    ensureCtx();
    vibrate(20);
    setWinner(null);

    const index = pickIndex(count);
    pendingWinner.current = segments[index];

    const jitter = (randomUnit() - 0.5) * JITTER_SPAN;
    const targetMod = winnerAngleRad(index, count, jitter);
    startSpin({ targetMod, segments: count, gentle: prefersReducedMotion() });
  }, [current, isSpinning, count, segments, ensureCtx, startSpin]);

  // Gentle idle drift before the first spin (skipped under reduced motion).
  const idleStarted = useRef(false);
  useEffect(() => {
    if (idleStarted.current) return;
    if (count < 2) return;
    if (typeof window === 'undefined' || prefersReducedMotion()) return;
    idleStarted.current = true;
    startIdle(count);
  }, [count, startIdle]);

  const closeWinner = useCallback(() => setWinner(null), []);
  const spinAgain = useCallback(() => {
    setWinner(null);
    spin();
  }, [spin]);

  return (
    <div className="min-h-screen supports-[height:100dvh]:min-h-[100dvh] bg-gradient-to-b from-[#160c2b] to-[#2a1414] text-white">
      <header className="flex items-center justify-between px-4 py-3">
        <Link href="/dashboard" className="text-sm text-white/60 hover:text-white">
          ← {t('backToDashboard')}
        </Link>
        <h1 className="text-lg font-bold tracking-wide">{t('title')}</h1>
        <button
          type="button"
          onClick={() => setEditing((v) => !v)}
          className="rounded-full bg-white/10 px-4 py-1.5 text-sm font-semibold hover:bg-white/20"
        >
          {editing ? t('closeEditor') : t('editWheel')}
        </button>
      </header>

      <main className="flex flex-col items-center gap-6 px-4 pb-10">
        {current && (
          <p className="text-sm text-white/60">{current.name}</p>
        )}

        {isSpinnable(current) ? (
          <div className="relative flex w-full items-center justify-center py-4">
            <Wheel
              segments={segments}
              discRef={discRef}
              spinning={isSpinning}
              spinLabel={isSpinning ? t('spinning') : t('spin')}
              disabled={!canSpin}
              onSpin={spin}
            />
          </div>
        ) : (
          <div className="mt-16 max-w-sm text-center text-white/70">
            <p className="mb-4">{t('emptyWheel')}</p>
            <button
              type="button"
              onClick={() => setEditing(true)}
              className="rounded-full bg-emerald-600 px-6 py-2 font-bold hover:bg-emerald-500"
            >
              {t('editWheel')}
            </button>
          </div>
        )}

        {editing && <ConfigEditor presetsApi={presetsApi} onClose={() => setEditing(false)} />}
      </main>

      {winner && (
        <WinnerModal segment={winner} onClose={closeWinner} onSpinAgain={spinAgain} />
      )}
    </div>
  );
}
