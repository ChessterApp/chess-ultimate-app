'use client';

import { useEffect, useRef, useState } from 'react';
import { DotLottieReact, setWasmUrl } from '@lottiefiles/dotlottie-react';
import type { DotLottie } from '@lottiefiles/dotlottie-web';

setWasmUrl('/animations/dotlottie-player.wasm');

/** The four rigged fox states (spec §10.1 required-states subset for the slice). */
export type FoxState = 'idle' | 'greet' | 'celebrate' | 'hatch';

/** Lottie source per state (placeholder rig; real art is a parallel track). */
const LOTTIE_SRC: Record<FoxState, string> = {
  idle: '/animations/companion-fox-idle.json',
  greet: '/animations/companion-fox-greet.json',
  celebrate: '/animations/companion-fox-celebrate.json',
  hatch: '/animations/companion-fox-hatch.json',
};

/** Static SVG fallback per state — the guaranteed, accessible, no-canvas art. */
const STATIC_SRC: Record<FoxState, string> = {
  idle: '/gamification/companion-fox-idle.svg',
  greet: '/gamification/companion-fox-greet.svg',
  celebrate: '/gamification/companion-fox-celebrate.svg',
  hatch: '/gamification/companion-fox-hatch.svg',
};

interface CompanionAnimationProps {
  state: FoxState;
  /** Accessible label (localized by the caller). */
  label: string;
  size?: number;
  /** Loop the Lottie (idle/greet/celebrate); the hatch scene plays once. */
  loop?: boolean;
  /** Fired when a non-looping (hatch) animation finishes OR its static-fallback
   *  timer elapses — lets the reveal advance to the next phase. */
  onComplete?: () => void;
}

/**
 * The fox companion animation (Phase 3). Renders a looping/one-shot placeholder
 * Lottie when motion is allowed and the file loads; otherwise the static SVG
 * fallback — chosen when `prefers-reduced-motion` is set, the Lottie fails to
 * load, or we render server-side (spec §10.1 accessibility fallback). Mirrors the
 * Phase 1 EggAnimation + the items.anim_url (animated) / art_url (static) pattern.
 */
export default function CompanionAnimation({
  state,
  label,
  size = 200,
  loop = true,
  onComplete,
}: CompanionAnimationProps) {
  const [animate, setAnimate] = useState(false);
  const [failed, setFailed] = useState(false);
  const dotLottie = useRef<DotLottie | null>(null);

  // Opt into motion only on the client, when matchMedia exists and reduced
  // motion is NOT requested. Server render + jsdom (no matchMedia) stay static.
  useEffect(() => {
    if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return;
    const mq = window.matchMedia('(prefers-reduced-motion: reduce)');
    const apply = () => setAnimate(!mq.matches);
    apply();
    mq.addEventListener?.('change', apply);
    return () => mq.removeEventListener?.('change', apply);
  }, []);

  const showLottie = animate && !failed;

  // When motion is off/failed and the scene is one-shot, still notify completion
  // after a short beat so the reveal flow never stalls on the static fallback.
  useEffect(() => {
    if (showLottie || loop || !onComplete) return;
    const timer = setTimeout(onComplete, 900);
    return () => clearTimeout(timer);
  }, [showLottie, loop, onComplete]);

  return (
    <div
      role="img"
      aria-label={label}
      style={{ width: size, height: size }}
      className="relative mx-auto flex items-center justify-center"
    >
      {showLottie ? (
        <DotLottieReact
          key={state}
          src={LOTTIE_SRC[state]}
          loop={loop}
          autoplay
          dotLottieRefCallback={(dl) => {
            dotLottie.current = dl;
            dl?.addEventListener('loadError', () => setFailed(true));
            if (!loop && onComplete) dl?.addEventListener('complete', onComplete);
          }}
          style={{ width: '100%', height: '100%' }}
        />
      ) : (
        // eslint-disable-next-line @next/next/no-img-element -- static SVG fallback asset
        <img src={STATIC_SRC[state]} alt="" width={size} height={size} aria-hidden="true" />
      )}
    </div>
  );
}
