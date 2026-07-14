'use client';

import React, { useEffect, useState } from 'react';
import { DotLottieReact, setWasmUrl } from '@lottiefiles/dotlottie-react';

setWasmUrl('/animations/dotlottie-player.wasm');

interface LottieCelebrationProps {
  /** Whether the celebration animation is visible */
  visible: boolean;
  /** Duration in milliseconds before auto-hiding (default: 1500) */
  duration?: number;
  /** Callback when animation completes */
  onComplete?: () => void;
  /**
   * Cover the whole viewport (fixed) instead of the centered board overlay.
   * Used behind the game-end result modal; defaults to the puzzle-board layout.
   */
  fullScreen?: boolean;
}

/**
 * LottieCelebration - Displays a celebratory Lottie animation overlay.
 * By default it centers over the chess board when the user solves a puzzle; in
 * `fullScreen` mode it covers the viewport (e.g. confetti behind a result modal).
 * Uses local .lottie file for reliable loading without external dependencies.
 */
export default function LottieCelebration({
  visible,
  duration = 1500,
  onComplete,
  fullScreen = false,
}: LottieCelebrationProps) {
  const [show, setShow] = useState(visible);

  useEffect(() => {
    if (visible) {
      setShow(true);
      // Auto-hide after duration
      const timer = setTimeout(() => {
        setShow(false);
        onComplete?.();
      }, duration);
      return () => clearTimeout(timer);
    } else {
      setShow(false);
    }
  }, [visible, duration, onComplete]);

  if (!show) return null;

  const containerStyle: React.CSSProperties = fullScreen
    ? {
        position: 'fixed',
        inset: 0,
        zIndex: 1310,
        pointerEvents: 'none',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
      }
    : {
        position: 'absolute',
        top: '50%',
        left: '50%',
        transform: 'translate(-50%, -50%)',
        width: '50%',
        height: '50%',
        zIndex: 100,
        pointerEvents: 'none',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
      };

  return (
    <div style={containerStyle}>
      <DotLottieReact
        src="/animations/celebration.lottie"
        loop={false}
        autoplay
        style={{
          width: '100%',
          height: '100%',
        }}
      />
    </div>
  );
}
