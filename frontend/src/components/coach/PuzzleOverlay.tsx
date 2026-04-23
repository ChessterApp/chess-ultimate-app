'use client';

import React, { useEffect, useState } from 'react';

interface PuzzleOverlayProps {
  result: 'correct' | 'wrong' | 'solved' | null;
  onDismiss: () => void;
}

export default function PuzzleOverlay({ result, onDismiss }: PuzzleOverlayProps) {
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    if (result) {
      setVisible(true);
      const timer = setTimeout(() => {
        setVisible(false);
        onDismiss();
      }, result === 'solved' ? 2000 : 1200);
      return () => clearTimeout(timer);
    }
  }, [result, onDismiss]);

  if (!visible || !result) return null;

  const config = {
    correct: {
      icon: '✓',
      text: 'Correct!',
      bg: 'bg-green-500/20',
      border: 'border-green-500/50',
      textColor: 'text-green-400',
    },
    wrong: {
      icon: '✗',
      text: 'Try again',
      bg: 'bg-red-500/20',
      border: 'border-red-500/50',
      textColor: 'text-red-400',
    },
    solved: {
      icon: '★',
      text: 'Puzzle solved!',
      bg: 'bg-yellow-500/20',
      border: 'border-yellow-500/50',
      textColor: 'text-yellow-400',
    },
  }[result];

  return (
    <div className="absolute inset-0 flex items-center justify-center pointer-events-none z-10">
      <div
        className={`${config.bg} ${config.border} border rounded-xl px-6 py-4 backdrop-blur-sm animate-fade-in`}
      >
        <div className={`text-center ${config.textColor}`}>
          <div className="text-3xl mb-1">{config.icon}</div>
          <div className="text-lg font-semibold">{config.text}</div>
        </div>
      </div>
    </div>
  );
}
