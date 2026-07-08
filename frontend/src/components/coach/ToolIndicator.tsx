'use client';

import React from 'react';
import { useTranslations } from 'next-intl';

interface ToolIndicatorProps {
  toolName: string;
  visible: boolean;
}

// Maps a raw backend tool name to a translation key in the `coach` namespace.
// Unknown tools fall back to a generic "Working…" label.
const TOOL_LABEL_KEY: Record<string, string> = {
  board_control: 'toolBoardControl',
  find_critical_moments: 'toolCriticalMoments',
  // search / lookup tools
  search_master_games: 'toolSearchGames',
  get_game_pgn: 'toolSearchGames',
  get_opening_stats: 'toolSearchGames',
  get_position_stats: 'toolSearchGames',
  get_player_openings: 'toolSearchGames',
  get_player_profile: 'toolSearchGames',
  get_user_games: 'toolSearchGames',
  get_user_repertoire: 'toolSearchGames',
  opponent_prep: 'toolSearchGames',
  search_web: 'toolSearchWeb',
  // analysis tools
  analyze_position: 'toolAnalyzing',
  compare_variations: 'toolAnalyzing',
  score_position_themes: 'toolAnalyzing',
  weakness_tracker: 'toolAnalyzing',
};

export default function ToolIndicator({ toolName, visible }: ToolIndicatorProps) {
  const t = useTranslations('coach');

  if (!visible) return null;

  const key = TOOL_LABEL_KEY[toolName] ?? 'toolWorking';
  const label = t(key);

  return (
    <div className="flex items-center gap-2 px-3 py-1.5 bg-white/5 rounded-lg text-sm text-gray-400 animate-pulse">
      <svg
        className="animate-spin h-4 w-4"
        viewBox="0 0 24 24"
        fill="none"
      >
        <circle
          className="opacity-25"
          cx="12"
          cy="12"
          r="10"
          stroke="currentColor"
          strokeWidth="4"
        />
        <path
          className="opacity-75"
          fill="currentColor"
          d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
        />
      </svg>
      <span>{label}</span>
    </div>
  );
}
