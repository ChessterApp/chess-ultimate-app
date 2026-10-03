'use client';

import { useEffect, useRef, useState } from 'react';
import { DotLottieReact, setWasmUrl } from '@lottiefiles/dotlottie-react';
import type { DotLottie } from '@lottiefiles/dotlottie-web';
import { eggVariant } from '@/lib/companion/state';

setWasmUrl('/animations/dotlottie-player.wasm');

const EGG_LOTTIE_SRC = '/animations/companion-egg.json';

interface EggAnimationProps {
  /** Chosen egg variant id (companion.species); falls back to the fox colour. */
  species?: string | null;
  /** Accessible label for the egg (localized by the caller). */
  label: string;
  size?: number;
}

/**
 * The idle egg. Renders a looping placeholder Lottie when motion is allowed and
 * the animation loads; otherwise a static SVG egg (the spec-required fallback)
 * when `prefers-reduced-motion` is set, the Lottie fails to load, or we are
 * server-side. The egg shell is tinted by the chosen variant colour.
 */
export default function EggAnimation({ species, label, size = 180 }: EggAnimationProps) {
  const color = eggVariant(species)?.color ?? '#f97316';
  const [animate, setAnimate] = useState(false);
  const [failed, setFailed] = useState(false);
  const dotLottie = useRef<DotLottie | null>(null);

  // Only opt into motion on the client, when matchMedia exists and reduced
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

  return (
    <div
      role="img"
      aria-label={label}
      style={{ width: size, height: size }}
      className="relative mx-auto flex items-center justify-center"
    >
      {showLottie ? (
        <DotLottieReact
          src={EGG_LOTTIE_SRC}
          loop
          autoplay
          dotLottieRefCallback={(dl) => {
            dotLottie.current = dl;
            dl?.addEventListener('loadError', () => setFailed(true));
          }}
          style={{ width: '100%', height: '100%' }}
        />
      ) : (
        <EggStatic color={color} size={size} />
      )}
    </div>
  );
}

/** Static SVG egg — the guaranteed fallback art (no animation, no canvas). */
function EggStatic({ color, size }: { color: string; size: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 200 200"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden="true"
    >
      <ellipse cx="100" cy="155" rx="55" ry="12" fill="rgba(0,0,0,0.08)" />
      <path
        d="M100 28c-34 0-56 48-56 86a56 56 0 0 0 112 0c0-38-22-86-56-86z"
        fill={color}
      />
      <path
        d="M100 28c-34 0-56 48-56 86a56 56 0 0 0 28 48C58 150 54 120 62 96c7-22 22-44 38-54-0-7-0-11 0-14z"
        fill="rgba(255,255,255,0.22)"
      />
      <circle cx="82" cy="104" r="6" fill="rgba(255,255,255,0.5)" />
      <circle cx="120" cy="128" r="4" fill="rgba(255,255,255,0.4)" />
    </svg>
  );
}
