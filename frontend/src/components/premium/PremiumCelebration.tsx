'use client';

import { useEffect, useRef, useState, useCallback } from 'react';
import confetti from 'canvas-confetti';

/**
 * One-time "Welcome to Premium" ceremony overlay.
 *
 * Port of the approved v3 prototype
 * (clawd/files/design/chesster-congrats/v3-animated.html): dark gray-900
 * full-viewport scene, gold radial glow bloom, crown spring drop-in, receipt
 * card whose rows print in sequentially, PREMIUM badge shimmer, and a gold
 * "Let's go" CTA with a soft pulse. Choreography is ~3.5s total.
 *
 * Confetti is two angled gold cannons fired beside the crown (one-shot, ~2–3s),
 * on a canvas that never captures pointer events or focus. `prefers-reduced-
 * motion` renders everything instantly and skips the confetti.
 */

const GOLD = ['#FDE68A', '#F59E0B', '#FBBF24', '#D97706', '#FFFFFF'];

interface PremiumCelebrationProps {
  email: string;
  planLabel: string;
  /** ISO/date string the subscription runs until; null → "Unlimited". */
  accessUntil: string | null;
  onDismiss: () => void;
}

function formatAccess(accessUntil: string | null): string {
  if (!accessUntil) return 'Unlimited';
  const d = new Date(accessUntil);
  if (Number.isNaN(d.getTime())) return accessUntil;
  return d.toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  });
}

export default function PremiumCelebration({
  email,
  planLabel,
  accessUntil,
  onDismiss,
}: PremiumCelebrationProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const headingRef = useRef<HTMLHeadingElement>(null);
  const [play, setPlay] = useState(false);

  // Lock body scroll while the ceremony is mounted.
  useEffect(() => {
    const prev = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.body.style.overflow = prev;
    };
  }, []);

  // Move focus to the heading on mount so screen readers announce the ceremony
  // and keyboard focus is trapped inside the dialog.
  useEffect(() => {
    headingRef.current?.focus();
  }, []);

  // Escape dismisses.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onDismiss();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onDismiss]);

  // Start the choreography once fonts are ready so nothing pops in mid-scene,
  // then fire the confetti synced with the headline reveal (~0.7s in).
  useEffect(() => {
    const reduced =
      typeof window !== 'undefined' &&
      window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    let burstTimer: ReturnType<typeof setTimeout> | undefined;
    let sparkleTimer: ReturnType<typeof setTimeout> | undefined;

    const start = () => {
      setPlay(true);
      if (reduced || !canvasRef.current) return;

      const fire = confetti.create(canvasRef.current, {
        resize: true,
        disableForReducedMotion: true,
      });

      const burst = () => {
        // Two angled cannons from just beside the crown.
        fire({
          particleCount: 70,
          angle: 60,
          spread: 58,
          startVelocity: 48,
          origin: { x: 0.32, y: 0.26 },
          colors: GOLD,
          ticks: 190,
          gravity: 0.95,
          scalar: 0.95,
        });
        fire({
          particleCount: 70,
          angle: 120,
          spread: 58,
          startVelocity: 48,
          origin: { x: 0.68, y: 0.26 },
          colors: GOLD,
          ticks: 190,
          gravity: 0.95,
          scalar: 0.95,
        });
        // Soft sparkle drift above the crown.
        sparkleTimer = setTimeout(
          () =>
            fire({
              particleCount: 26,
              spread: 110,
              startVelocity: 16,
              origin: { x: 0.5, y: 0.2 },
              colors: GOLD,
              ticks: 230,
              gravity: 0.5,
              scalar: 0.6,
              shapes: ['circle'],
            }),
          220,
        );
      };

      burstTimer = setTimeout(burst, 700);
    };

    let cancelled = false;
    const raf = requestAnimationFrame(() => {
      const fonts = (document as Document & { fonts?: FontFaceSet }).fonts;
      if (fonts?.ready) {
        fonts.ready.then(() => {
          if (!cancelled) start();
        });
      } else {
        start();
      }
    });

    return () => {
      cancelled = true;
      cancelAnimationFrame(raf);
      if (burstTimer) clearTimeout(burstTimer);
      if (sparkleTimer) clearTimeout(sparkleTimer);
    };
  }, []);

  const handleDismiss = useCallback(() => onDismiss(), [onDismiss]);

  return (
    <div
      className={`pc-root${play ? ' play' : ''}`}
      role="dialog"
      aria-modal="true"
      aria-label="Welcome to Premium"
    >
      <canvas ref={canvasRef} className="pc-confetti" aria-hidden="true" />
      <div className="pc-glow" aria-hidden="true" />
      <div className="pc-queen" aria-hidden="true">
        ♛
      </div>
      <h1 ref={headingRef} className="pc-h1" tabIndex={-1} aria-live="polite">
        Welcome to Premium
      </h1>
      <p className="pc-sub">
        Your account has been updated. Full access to everything — unlocked.
      </p>
      <div className="pc-receipt" role="status" aria-live="polite">
        <div className="pc-head">
          <span className="pc-head-t">Membership</span>
          <span className="pc-badge">
            PREMIUM<span className="pc-shine" />
          </span>
        </div>
        <div className="pc-r">
          <span className="pc-k">Member</span>
          <span className="pc-v">{email}</span>
        </div>
        <div className="pc-r">
          <span className="pc-k">Plan</span>
          <span className="pc-v">{planLabel}</span>
        </div>
        <div className="pc-r">
          <span className="pc-k">Status</span>
          <span className="pc-v pc-gold">Active</span>
        </div>
        <div className="pc-r">
          <span className="pc-k">Access until</span>
          <span className="pc-v">{formatAccess(accessUntil)}</span>
        </div>
      </div>
      <button type="button" className="pc-cta" onClick={handleDismiss}>
        Let&rsquo;s go
      </button>

      <style jsx>{`
        .pc-root {
          --paper: #18181b;
          --paper-2: #1f1f23;
          --ink: #fafafa;
          --ink-2: #a1a1aa;
          --ink-3: #71717a;
          --hairline: rgb(255 255 255 / 0.12);
          --hairline-soft: rgb(255 255 255 / 0.07);
          --gold: #f59e0b;
          --gold-soft: #fde68a;
          --spring: cubic-bezier(0.34, 1.56, 0.64, 1);
          position: fixed;
          inset: 0;
          z-index: 2000;
          background: var(--paper);
          color: var(--ink);
          font-family: var(--font-geist-sans), Inter, system-ui, sans-serif;
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          padding: 0 26px;
          text-align: center;
          overflow: clip;
        }
        .pc-confetti {
          position: absolute;
          inset: 0;
          pointer-events: none;
          z-index: 5;
        }
        .pc-glow {
          position: absolute;
          top: 8%;
          left: 50%;
          width: 340px;
          height: 340px;
          margin-left: -170px;
          border-radius: 50%;
          background: radial-gradient(
            circle,
            rgb(245 158 11 / 0.16),
            transparent 65%
          );
          pointer-events: none;
          opacity: 0;
          transform: scale(0.4);
        }
        .pc-queen {
          font-size: 84px;
          line-height: 1;
          background: linear-gradient(180deg, var(--gold-soft), var(--gold));
          -webkit-background-clip: text;
          background-clip: text;
          color: transparent;
          margin-bottom: 22px;
          position: relative;
          opacity: 0;
        }
        .pc-h1 {
          font-size: 28px;
          font-weight: 700;
          letter-spacing: -0.02em;
          margin-bottom: 10px;
          opacity: 0;
          outline: none;
        }
        .pc-sub {
          font-size: 14.5px;
          color: var(--ink-2);
          line-height: 1.55;
          max-width: 280px;
          margin-bottom: 34px;
          opacity: 0;
        }
        .pc-receipt {
          width: 100%;
          max-width: 338px;
          background: var(--paper-2);
          border: 1px solid var(--hairline);
          border-radius: 1.5rem;
          padding: 22px 20px;
          text-align: left;
          opacity: 0;
        }
        .pc-head {
          display: flex;
          justify-content: space-between;
          align-items: center;
          padding-bottom: 14px;
          border-bottom: 1px solid var(--hairline-soft);
        }
        .pc-head-t {
          font-size: 13px;
          font-weight: 600;
          letter-spacing: 0.02em;
        }
        .pc-badge {
          font-size: 11px;
          font-weight: 700;
          color: var(--paper);
          background: linear-gradient(135deg, var(--gold-soft), var(--gold));
          padding: 5px 11px;
          border-radius: 9999px;
          position: relative;
          overflow: hidden;
          opacity: 0;
        }
        .pc-shine {
          position: absolute;
          inset: 0;
          background: linear-gradient(
            115deg,
            transparent 30%,
            rgb(255 255 255 / 0.75) 50%,
            transparent 70%
          );
          transform: translateX(-120%);
        }
        .pc-r {
          display: flex;
          justify-content: space-between;
          padding: 11px 0;
          border-bottom: 1px solid var(--hairline-soft);
          opacity: 0;
        }
        .pc-r:last-of-type {
          border-bottom: none;
        }
        .pc-k {
          font-size: 12.5px;
          color: var(--ink-3);
        }
        .pc-v {
          font-size: 12.5px;
          font-family: var(--font-geist-mono), ui-monospace, monospace;
          color: var(--ink);
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
          max-width: 190px;
        }
        .pc-v.pc-gold {
          color: var(--gold);
        }
        .pc-cta {
          width: 100%;
          max-width: 338px;
          margin-top: 30px;
          background: linear-gradient(135deg, var(--gold-soft), var(--gold));
          color: #1c1917;
          border: none;
          font: inherit;
          font-size: 15.5px;
          font-weight: 700;
          padding: 16px;
          border-radius: 9999px;
          opacity: 0;
          cursor: pointer;
        }

        @keyframes pc-bloom {
          from {
            opacity: 0;
            transform: scale(0.4);
          }
          to {
            opacity: 1;
            transform: scale(1);
          }
        }
        @keyframes pc-glowPulse {
          0%,
          100% {
            opacity: 1;
          }
          50% {
            opacity: 0.72;
          }
        }
        @keyframes pc-crownDrop {
          0% {
            opacity: 0;
            transform: translateY(-90px) scale(0.6);
          }
          60% {
            opacity: 1;
            transform: translateY(8px) scale(1.06);
          }
          80% {
            transform: translateY(-4px) scale(0.98);
          }
          100% {
            opacity: 1;
            transform: translateY(0) scale(1);
          }
        }
        @keyframes pc-crownGlow {
          0% {
            filter: drop-shadow(0 0 0 rgb(245 158 11 / 0));
          }
          45% {
            filter: drop-shadow(0 0 26px rgb(245 158 11 / 0.55));
          }
          100% {
            filter: drop-shadow(0 0 12px rgb(245 158 11 / 0.25));
          }
        }
        @keyframes pc-fadeUp {
          from {
            opacity: 0;
            transform: translateY(16px);
          }
          to {
            opacity: 1;
            transform: translateY(0);
          }
        }
        @keyframes pc-cardUp {
          from {
            opacity: 0;
            transform: translateY(44px) scale(0.97);
          }
          to {
            opacity: 1;
            transform: translateY(0) scale(1);
          }
        }
        @keyframes pc-rowIn {
          from {
            opacity: 0;
            transform: translateX(-10px);
          }
          to {
            opacity: 1;
            transform: translateX(0);
          }
        }
        @keyframes pc-badgeLand {
          0% {
            opacity: 0;
            transform: scale(1.7);
          }
          70% {
            opacity: 1;
            transform: scale(0.94);
          }
          100% {
            opacity: 1;
            transform: scale(1);
          }
        }
        @keyframes pc-shineSweep {
          to {
            transform: translateX(120%);
          }
        }
        @keyframes pc-ctaIn {
          from {
            opacity: 0;
            transform: translateY(14px);
          }
          to {
            opacity: 1;
            transform: translateY(0);
          }
        }
        @keyframes pc-ctaPulse {
          0%,
          100% {
            box-shadow: 0 0 0 0 rgb(245 158 11 / 0.45);
          }
          60% {
            box-shadow: 0 0 0 14px rgb(245 158 11 / 0);
          }
        }

        .play .pc-glow {
          animation:
            pc-bloom 0.7s ease-out forwards,
            pc-glowPulse 3.2s ease-in-out 0.7s infinite;
        }
        .play .pc-queen {
          animation:
            pc-crownDrop 0.75s var(--spring) 0.15s forwards,
            pc-crownGlow 1.1s ease-out 0.35s forwards;
        }
        .play .pc-h1 {
          animation: pc-fadeUp 0.55s ease-out 0.65s forwards;
        }
        .play .pc-sub {
          animation: pc-fadeUp 0.55s ease-out 0.85s forwards;
        }
        .play .pc-receipt {
          animation: pc-cardUp 0.65s var(--spring) 1.2s forwards;
        }
        .play .pc-r:nth-of-type(2) {
          animation: pc-rowIn 0.4s ease-out 1.5s forwards;
        }
        .play .pc-r:nth-of-type(3) {
          animation: pc-rowIn 0.4s ease-out 1.68s forwards;
        }
        .play .pc-r:nth-of-type(4) {
          animation: pc-rowIn 0.4s ease-out 1.86s forwards;
        }
        .play .pc-r:nth-of-type(5) {
          animation: pc-rowIn 0.4s ease-out 2.04s forwards;
        }
        .play .pc-badge {
          animation: pc-badgeLand 0.5s var(--spring) 2.25s forwards;
        }
        .play .pc-shine {
          animation: pc-shineSweep 0.7s ease-in-out 2.75s forwards;
        }
        .play .pc-cta {
          animation:
            pc-ctaIn 0.5s ease-out 2.5s forwards,
            pc-ctaPulse 2.2s ease-out 3.1s 2;
        }

        @media (prefers-reduced-motion: reduce) {
          .play :global(*) {
            animation: none !important;
          }
          .play .pc-glow,
          .play .pc-queen,
          .play .pc-h1,
          .play .pc-sub,
          .play .pc-receipt,
          .play .pc-r,
          .play .pc-badge,
          .play .pc-cta {
            opacity: 1;
            transform: none;
          }
        }
      `}</style>
    </div>
  );
}
