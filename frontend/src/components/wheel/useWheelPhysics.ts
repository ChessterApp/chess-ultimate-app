'use client';

// rAF driver for the wheel physics engine. Runs a fixed-timestep accumulator
// (60 logical ticks/sec) inside requestAnimationFrame and writes the disc's
// rotation straight to the DOM via a ref — no React re-render per frame and no
// CSS transition. Emits a callback on each real boundary crossing (tick sound)
// and one on entering the Stopped phase (winner reveal + confetti).

import { useCallback, useEffect, useRef, useState } from 'react';
import { WheelPhysics, DEFAULT_SPIN_TIME } from '@/lib/wheel/physics';

const RAD_TO_DEG = 180 / Math.PI;
const FIXED_DT_MS = 1000 / 60; // one logical tick
const MAX_TICKS_PER_FRAME = 6; // spiral-of-death guard
const MAX_FRAME_DELTA_MS = 250; // clamp huge gaps (backgrounded tab)

export interface StartSpinParams {
  /** Final angle mod 2π (radians) that lands the pre-chosen winner. */
  targetMod: number;
  /** Segment count. */
  segments: number;
  /** Reduced-motion gentle spin. */
  gentle?: boolean;
  /** Total spin duration, seconds. */
  spinTime?: number;
}

export interface UseWheelPhysicsOptions {
  /** Called once per real slice-boundary crossing (drives the tick sound). */
  onCrossing?: () => void;
  /** Called on the instant the wheel enters the Stopped phase. */
  onStopped?: () => void;
}

export function useWheelPhysics({ onCrossing, onStopped }: UseWheelPhysicsOptions = {}) {
  const discRef = useRef<HTMLDivElement | null>(null);
  const physicsRef = useRef<WheelPhysics | null>(null);
  const rafRef = useRef<number | null>(null);
  const lastTsRef = useRef<number | null>(null);
  const accRef = useRef(0);
  const [isSpinning, setIsSpinning] = useState(false);

  // Keep the latest callbacks without re-creating the rAF loop.
  const onCrossingRef = useRef(onCrossing);
  const onStoppedRef = useRef(onStopped);
  useEffect(() => {
    onCrossingRef.current = onCrossing;
    onStoppedRef.current = onStopped;
  }, [onCrossing, onStopped]);

  const writeTransform = useCallback((angleRad: number) => {
    const el = discRef.current;
    if (el) el.style.transform = `rotate(${angleRad * RAD_TO_DEG}deg)`;
  }, []);

  const stopLoop = useCallback(() => {
    if (rafRef.current != null) cancelAnimationFrame(rafRef.current);
    rafRef.current = null;
    lastTsRef.current = null;
    accRef.current = 0;
  }, []);

  // The rAF callback is held in a ref so it can re-schedule itself without the
  // loop closure referencing its own binding (keeps hook deps clean).
  const loopRef = useRef<(ts: number) => void>(() => {});

  const schedule = useCallback(() => {
    rafRef.current = requestAnimationFrame((ts) => loopRef.current(ts));
  }, []);

  const loop = useCallback(
    (ts: number) => {
      const phys = physicsRef.current;
      if (!phys) {
        stopLoop();
        return;
      }
      if (lastTsRef.current == null) lastTsRef.current = ts;
      let delta = ts - lastTsRef.current;
      lastTsRef.current = ts;
      if (delta > MAX_FRAME_DELTA_MS) delta = FIXED_DT_MS;
      accRef.current += delta;

      let ticks = 0;
      let stopped = false;
      while (accRef.current >= FIXED_DT_MS && ticks < MAX_TICKS_PER_FRAME) {
        const r = phys.tick();
        accRef.current -= FIXED_DT_MS;
        ticks += 1;
        if (
          r.crossings > 0 &&
          (r.phase === 'accelerating' || r.phase === 'decelerating')
        ) {
          for (let i = 0; i < r.crossings; i++) onCrossingRef.current?.();
        }
        if (r.justStopped) {
          stopped = true;
          break;
        }
      }
      // Drop any backlog so we never fast-forward after a stall.
      if (accRef.current > FIXED_DT_MS * MAX_TICKS_PER_FRAME) accRef.current = 0;

      writeTransform(phys.angle);

      if (stopped) {
        setIsSpinning(false);
        stopLoop();
        onStoppedRef.current?.();
        return;
      }
      schedule();
    },
    [stopLoop, writeTransform, schedule],
  );

  useEffect(() => {
    loopRef.current = loop;
  }, [loop]);

  const startLoop = useCallback(() => {
    if (rafRef.current == null) schedule();
  }, [schedule]);

  /** Begin a real spin that lands on the winner encoded by `targetMod`. */
  const spin = useCallback(
    ({ targetMod, segments, gentle = false, spinTime = DEFAULT_SPIN_TIME }: StartSpinParams) => {
      const current = physicsRef.current?.angle ?? 0;
      const targetFinalAngle = WheelPhysics.resolveTarget({
        startAngle: current,
        targetMod,
        gentle,
        spinTime,
      });

      physicsRef.current = WheelPhysics.spin({
        spinTime,
        targetFinalAngle,
        segments,
        gentle,
        startAngle: current,
      });
      setIsSpinning(true);
      stopLoop();
      startLoop();
    },
    [startLoop, stopLoop],
  );

  /** Start the gentle continuous idle drift (before the first spin). */
  const startIdle = useCallback(
    (segments: number) => {
      if (isSpinning) return;
      const current = physicsRef.current?.angle ?? 0;
      physicsRef.current = WheelPhysics.idle(segments, current);
      startLoop();
    },
    [isSpinning, startLoop],
  );

  useEffect(() => {
    writeTransform(physicsRef.current?.angle ?? 0);
    return () => stopLoop();
  }, [writeTransform, stopLoop]);

  return { discRef, spin, startIdle, isSpinning };
}
