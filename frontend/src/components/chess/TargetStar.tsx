'use client';

import React from 'react';

interface TargetStarProps {
  square: string;
  orientation?: 'white' | 'black';
  visible?: boolean;
}

function getSquarePosition(square: string, orientation: 'white' | 'black') {
  const file = square.charCodeAt(0) - 'a'.charCodeAt(0);
  const rank = parseInt(square[1]) - 1;
  const x = orientation === 'white' ? file : 7 - file;
  const y = orientation === 'white' ? 7 - rank : rank;
  return {
    left: `${x * 12.5 + 6.25}%`,
    top: `${y * 12.5 + 6.25}%`,
  };
}

export default function TargetStar({ square, orientation = 'white', visible = true }: TargetStarProps) {
  if (!visible || !square) return null;

  const position = getSquarePosition(square, orientation);
  const uniqueId = `star-${square}`;

  return (
    <div
      style={{
        position: 'absolute',
        left: position.left,
        top: position.top,
        width: '15%',
        height: '15%',
        transform: 'translate(-50%, -50%)',
        zIndex: 200,
        pointerEvents: 'none',
        animation: 'star-pulse 1.7s ease-in-out infinite',
      }}
    >
      <style>{`
        @keyframes star-pulse {
          0%, 100% { transform: translate(-50%, -50%) scale(1); }
          50% { transform: translate(-50%, -50%) scale(1.15); }
        }
      `}</style>
      <svg viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg" style={{ width: '100%', height: '100%', filter: 'drop-shadow(0 2px 6px rgba(0,0,0,0.4))' }}>
        <defs>
          <radialGradient id={`${uniqueId}-gold`} cx="50%" cy="40%" r="60%" fx="50%" fy="30%">
            <stop offset="0%" stopColor="#FFE343" />
            <stop offset="55%" stopColor="#FFE241" />
            <stop offset="100%" stopColor="#FED31E" />
          </radialGradient>
          <radialGradient id={`${uniqueId}-orange`} cx="50%" cy="60%" r="70%">
            <stop offset="0%" stopColor="#FF8000" stopOpacity="0" />
            <stop offset="100%" stopColor="#D86D00" />
          </radialGradient>
        </defs>
        <g transform="translate(50, 50) scale(3.5)">
          <path
            d="M0.52 -8.94L3.15 -3.61C3.18 -3.53 3.26 -3.48 3.34 -3.47L9.22 -2.61C9.69 -2.54 9.88 -1.96 9.54 -1.62L5.41 2.4C5.27 2.53 5.21 2.73 5.24 2.91L6.22 8.6C6.3 9.07 5.8 9.43 5.38 9.21L0.11 6.45C0.04 6.41 -0.05 6.41 -0.12 6.45L-5.38 9.21C-5.81 9.43 -6.3 9.07 -6.22 8.6L-5.21 2.74C-5.2 2.66 -5.22 2.58 -5.29 2.52L-9.54 -1.63C-9.88 -1.97 -9.69 -2.55 -9.22 -2.62L-3.34 -3.47C-3.26 -3.49 -3.18 -3.54 -3.15 -3.61L-0.52 -8.94C-0.31 -9.37 0.31 -9.37 0.52 -8.94Z"
            fill={`url(#${uniqueId}-gold)`}
          />
          <path
            d="M0.52 -8.94L3.15 -3.61C3.18 -3.53 3.26 -3.48 3.34 -3.47L9.22 -2.61C9.69 -2.54 9.88 -1.96 9.54 -1.62L5.41 2.4C5.27 2.53 5.21 2.73 5.24 2.91L6.22 8.6C6.3 9.07 5.8 9.43 5.38 9.21L0.11 6.45C0.04 6.41 -0.05 6.41 -0.12 6.45L-5.38 9.21C-5.81 9.43 -6.3 9.07 -6.22 8.6L-5.21 2.74C-5.2 2.66 -5.22 2.58 -5.29 2.52L-9.54 -1.63C-9.88 -1.97 -9.69 -2.55 -9.22 -2.62L-3.34 -3.47C-3.26 -3.49 -3.18 -3.54 -3.15 -3.61L-0.52 -8.94C-0.31 -9.37 0.31 -9.37 0.52 -8.94Z"
            fill={`url(#${uniqueId}-orange)`}
            opacity="0.5"
          />
        </g>
      </svg>
    </div>
  );
}
