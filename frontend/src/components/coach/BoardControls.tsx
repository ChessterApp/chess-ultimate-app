'use client';

import React from 'react';
import { useTranslations } from 'next-intl';

interface CoachBoardControlsProps {
  onFirst: () => void;
  onPrev: () => void;
  onNext: () => void;
  onLast: () => void;
  onFlip: () => void;
  canGoPrev: boolean;
  canGoNext: boolean;
}

export default function CoachBoardControls({
  onFirst,
  onPrev,
  onNext,
  onLast,
  onFlip,
  canGoPrev,
  canGoNext,
}: CoachBoardControlsProps) {
  const t = useTranslations('coach');
  const buttonClass =
    'px-3 py-2 rounded text-white transition-colors disabled:opacity-30 disabled:cursor-not-allowed';
  const activeClass = 'bg-white/10 hover:bg-white/20';

  return (
    <div className="flex items-center justify-center gap-1 mt-2">
      <button
        onClick={onFirst}
        disabled={!canGoPrev}
        className={`${buttonClass} ${canGoPrev ? activeClass : ''}`}
        title={`${t('firstMove')} (Home)`}
        aria-label={t('firstMove')}
      >
        <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
          <path d="M3 3v10h2V3H3zm3 5l8 5V3l-8 5z" />
        </svg>
      </button>

      <button
        onClick={onPrev}
        disabled={!canGoPrev}
        className={`${buttonClass} ${canGoPrev ? activeClass : ''}`}
        title={`${t('previousMove')} (←)`}
        aria-label={t('previousMove')}
      >
        <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
          <path d="M10 3L2 8l8 5V3z" />
        </svg>
      </button>

      <button
        onClick={onNext}
        disabled={!canGoNext}
        className={`${buttonClass} ${canGoNext ? activeClass : ''}`}
        title={`${t('nextMove')} (→)`}
        aria-label={t('nextMove')}
      >
        <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
          <path d="M6 3v10l8-5-8-5z" />
        </svg>
      </button>

      <button
        onClick={onLast}
        disabled={!canGoNext}
        className={`${buttonClass} ${canGoNext ? activeClass : ''}`}
        title={`${t('lastMove')} (End)`}
        aria-label={t('lastMove')}
      >
        <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
          <path d="M3 3l8 5-8 5V3zm8 0v10h2V3h-2z" />
        </svg>
      </button>

      <div className="w-px h-6 bg-white/20 mx-1" />

      <button
        onClick={onFlip}
        className={`${buttonClass} ${activeClass}`}
        title={`${t('flipBoard')} (F)`}
        aria-label={t('flipBoard')}
      >
        <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
          <path d="M8 1l3 4H9v3H7V5H5l3-4zM8 15l-3-4h2V8h2v3h2l-3 4z" />
        </svg>
      </button>
    </div>
  );
}
