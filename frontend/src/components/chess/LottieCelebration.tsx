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
}

/**
 * LottieCelebration - Displays a celebratory Lottie animation overlay
 * Shown in the center of the chess board when the user solves a puzzle
 * Uses local .lottie file for reliable loading without external dependencies
 */
export default function LottieCelebration({
  visible,
  duration = 1500,
  onComplete,
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

  return (
    <div
      style={{
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
      }}
    >
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
