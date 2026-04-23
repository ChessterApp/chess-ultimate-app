'use client';

import React from 'react';
import Link from 'next/link';
import { useSubscription } from '@/hooks/useSubscription';

interface CoachToggleProps {
  isCoachMode: boolean;
  onToggle: (enabled: boolean) => void;
}

export default function CoachToggle({ isCoachMode, onToggle }: CoachToggleProps) {
  const subscription = useSubscription();
  const isPremium = subscription.active;

  if (!isPremium) {
    return (
      <div className="relative group">
        <button
          disabled
          className="flex items-center gap-1.5 px-2 py-1 text-xs rounded bg-gray-700/50 text-gray-500 cursor-not-allowed"
        >
          <span>🎓</span>
          <span>Coach</span>
        </button>
        <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 px-3 py-1.5 bg-gray-900 text-white text-xs rounded-lg opacity-0 group-hover:opacity-100 transition-opacity whitespace-nowrap pointer-events-none">
          Upgrade to Premium for AI coaching
        </div>
      </div>
    );
  }

  return (
    <div className="flex items-center gap-2">
      <button
        onClick={() => onToggle(!isCoachMode)}
        className={`flex items-center gap-1.5 px-2 py-1 text-xs rounded transition-colors ${
          isCoachMode
            ? 'bg-indigo-600/30 text-indigo-300 border border-indigo-500/30'
            : 'bg-gray-700/50 text-gray-400 hover:bg-gray-700 hover:text-gray-300'
        }`}
        title={isCoachMode ? 'Switch to regular chat' : 'Switch to AI Coach mode'}
      >
        <span>🎓</span>
        <span>Coach{isCoachMode ? ' ON' : ''}</span>
      </button>
      {isCoachMode && (
        <Link
          href="/coach"
          className="text-xs text-indigo-400 hover:text-indigo-300 transition-colors"
          title="Open full coach page with board control"
        >
          Full page →
        </Link>
      )}
    </div>
  );
}
