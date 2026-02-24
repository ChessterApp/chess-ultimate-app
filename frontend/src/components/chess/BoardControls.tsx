/**
 * BoardControls Component
 *
 * Provides control buttons for the chess board (hint, reset)
 * with appropriate disabled states and animations
 */

import React from 'react';
import { useTranslations } from 'next-intl';

interface BoardControlsProps {
  /** Callback when hint button is clicked */
  onHint: () => void;
  /** Optional callback when reset button is clicked */
  onReset?: () => void;
  /** Whether the hint button should be disabled */
  hintDisabled?: boolean;
  /** Whether the reset button should be disabled */
  resetDisabled?: boolean;
  /** Optional CSS class name for styling */
  className?: string;
}

/**
 * BoardControls component provides hint and reset buttons
 * for chess exercises
 */
export default function BoardControls({
  onHint,
  onReset,
  hintDisabled = false,
  resetDisabled = false,
  className = '',
}: BoardControlsProps) {
  const t = useTranslations();
  return (
    <div className={`board-controls flex flex-wrap gap-2 mt-4 ${className}`}>
      <button
        onClick={onHint}
        disabled={hintDisabled}
        className="
          px-4
          py-2
          bg-yellow-500
          hover:bg-yellow-600
          text-white
          font-semibold
          rounded
          disabled:opacity-50
          disabled:cursor-not-allowed
          transition-colors
          duration-200
          button-press
          flex
          items-center
          gap-2
        "
        aria-label={t('lesson.showHint')}
      >
        <span aria-hidden="true">💡</span>
        {t('lesson.showHint')}
      </button>

      {onReset && (
        <button
          onClick={onReset}
          disabled={resetDisabled}
          className="
            px-4
            py-2
            bg-gray-500
            hover:bg-gray-600
            text-white
            font-semibold
            rounded
            disabled:opacity-50
            disabled:cursor-not-allowed
            transition-colors
            duration-200
            button-press
            flex
            items-center
            gap-2
          "
          aria-label={t('lesson.reset')}
        >
          <span aria-hidden="true">↻</span>
          {t('lesson.reset')}
        </button>
      )}
    </div>
  );
}
