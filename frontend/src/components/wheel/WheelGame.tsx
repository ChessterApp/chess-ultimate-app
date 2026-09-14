'use client';

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import Link from 'next/link';
import { useTranslations } from 'next-intl';
import { pickIndex } from '@/lib/wheel/random';
import { segmentAngle } from '@/lib/wheel/geometry';
import { isSpinnable } from '@/lib/wheel/presets';
import type { WheelSegment } from '@/lib/wheel/types';
import Wheel from './Wheel';
import WinnerModal from './WinnerModal';
import ConfigEditor from './ConfigEditor';
import { usePresets } from './usePresets';
import { useTickSound } from './useTickSound';
import { fireConfetti } from './confetti';

const MIN_DURATION = 4000;
const MAX_DURATION = 6000;

// One cubic component of a cubic-bezier curve with control points (0,p1,p2,1).
function bezierComponent(t: number, p1: number, p2: number): number {
  const c = 3 * p1;
  const b = 3 * (p2 - p1) - c;
  const a = 1 - c - b;
  return ((a * t + b) * t + c) * t;
}

// Matches the CSS easing on .wheel-disc: cubic-bezier(0.12, 0.75, 0.12, 1).
function easeTimeForValue(value: number): number {
  // Find parameter t where the y-component equals `value`, then map to the
  // x-component (elapsed-time fraction). Bisection is plenty accurate here.
  let lo = 0;
  let hi = 1;
  for (let i = 0; i < 24; i++) {
    const mid = (lo + hi) / 2;
    if (bezierComponent(mid, 0.75, 1) < value) lo = mid;
    else hi = mid;
  }
  const t = (lo + hi) / 2;
  return bezierComponent(t, 0.12, 0.12);
}

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

  const [rotation, setRotation] = useState(0);
  const [spinning, setSpinning] = useState(false);
  const [durationMs, setDurationMs] = useState(MIN_DURATION);
  const [winner, setWinner] = useState<WheelSegment | null>(null);
  const [editing, setEditing] = useState(false);

  const timers = useRef<ReturnType<typeof setTimeout>[]>([]);
  const clearTimers = useCallback(() => {
    timers.current.forEach(clearTimeout);
    timers.current = [];
  }, []);
  useEffect(() => clearTimers, [clearTimers]);

  const segments = useMemo(() => current?.segments ?? [], [current]);
  const count = segments.length;
  const canSpin = isSpinnable(current) && !spinning;

  const spin = useCallback(() => {
    if (!canSpin || count < 2) return;

    ensureCtx();
    vibrate(20);
    setWinner(null);

    const index = pickIndex(count);
    const seg = segmentAngle(count);
    const fullSpins = 4 + Math.floor(Math.random() * 3); // 4–6 revolutions
    const duration = MIN_DURATION + Math.random() * (MAX_DURATION - MIN_DURATION);

    // Absolute target angle for this segment's bisector (mod 360), then extend
    // forward from the current rotation so the disc always spins onward.
    const base = 360 - (index * seg + seg / 2);
    const currentMod = ((rotation % 360) + 360) % 360;
    const delta = fullSpins * 360 + ((base - currentMod + 360) % 360);
    const target = rotation + delta;

    setDurationMs(duration);
    setSpinning(true);
    setRotation(target);

    // Schedule ticks at each segment boundary crossing, timed to the easing.
    clearTimers();
    const boundaries = Math.min(Math.floor(delta / seg), 90);
    for (let b = 1; b <= boundaries; b++) {
      const valueFraction = (b * seg) / delta;
      const at = duration * easeTimeForValue(valueFraction);
      timers.current.push(setTimeout(tick, at));
    }

    // Settle: reveal the winner.
    timers.current.push(
      setTimeout(() => {
        setSpinning(false);
        setWinner(segments[index]);
        fireConfetti();
        vibrate([60, 40, 120]);
      }, duration + 60),
    );
  }, [canSpin, count, rotation, segments, ensureCtx, tick, clearTimers]);

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
              rotation={rotation}
              spinning={spinning}
              spinDurationMs={durationMs}
              spinLabel={spinning ? t('spinning') : t('spin')}
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
