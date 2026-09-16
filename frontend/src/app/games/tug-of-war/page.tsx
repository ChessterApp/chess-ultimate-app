/**
 * /games/tug-of-war — a public, client-side classroom team-battle chess game.
 * Milestone 1: playable core (two-board puzzle race + sliding rope scene).
 * Puzzles are prefetched live from /api/puzzle at match start — the match begins
 * as soon as a handful arrive and the rest stream in as it runs — with the
 * bundled TUG_PUZZLES set as an offline fallback. No auth, no backend of our own.
 */

'use client';

import { useReducer, useRef, useState } from 'react';
import { useTranslations } from 'next-intl';
import SetupScreen, { type StartConfig } from '@/components/tug-of-war/SetupScreen';
import MatchScreen from '@/components/tug-of-war/MatchScreen';
import { gameReducer, initialState } from '@/lib/tug-of-war/gameReducer';
import { prefetchPuzzles } from '@/lib/tug-of-war/prefetch';

export default function TugOfWarPage() {
  const t = useTranslations('tugOfWar');
  const [state, dispatch] = useReducer(
    gameReducer,
    undefined,
    () => initialState(t('defaultTeamA'), t('defaultTeamB')),
  );
  const [loading, setLoading] = useState(false);
  const [offline, setOffline] = useState(false);
  const [themesUnavailable, setThemesUnavailable] = useState(false);
  // Remember the last setup so the "retry live fetch" button can re-run it.
  const lastConfig = useRef<StartConfig | null>(null);

  const start = async (config: StartConfig) => {
    const { teamA, teamB, level, themes } = config;
    lastConfig.current = config;
    setLoading(true);
    setOffline(false);
    setThemesUnavailable(false);
    try {
      const { queueA, queueB, usedFallback, themesUnavailable: themesMissing } =
        await prefetchPuzzles({
          level,
          themes,
          // Top up each team's queue with live puzzles as they arrive.
          onTopUp: (deltaA, deltaB) =>
            dispatch({ type: 'APPEND_PUZZLES', queueA: deltaA, queueB: deltaB }),
        });
      setOffline(usedFallback);
      setThemesUnavailable(themesMissing);
      dispatch({ type: 'START_MATCH', teamAName: teamA, teamBName: teamB, queueA, queueB });
    } finally {
      setLoading(false);
    }
  };

  const retryLiveFetch = () => {
    if (lastConfig.current) void start(lastConfig.current);
  };

  return (
    <div className="relative min-h-screen bg-gradient-to-b from-slate-950 via-slate-900 to-slate-950">
      {state.phase === 'setup' ? (
        <SetupScreen
          initialTeamA={state.teamAName}
          initialTeamB={state.teamBName}
          onStart={start}
          loading={loading}
        />
      ) : (
        <MatchScreen state={state} dispatch={dispatch} />
      )}

      {offline && state.phase === 'match' && (
        themesUnavailable ? (
          // The theme filter could not be honored offline — be honest about it
          // and offer a live retry rather than silently serving off-theme puzzles.
          <div className="fixed bottom-4 left-1/2 z-30 flex -translate-x-1/2 items-center gap-3 rounded-xl border border-amber-400/40 bg-amber-500/15 px-4 py-2 text-xs font-semibold text-amber-100 shadow-lg backdrop-blur">
            <span>{t('offlineThemesUnavailable')}</span>
            <button
              type="button"
              onClick={retryLiveFetch}
              disabled={loading}
              className="rounded-full border border-amber-300/50 bg-amber-400/20 px-3 py-1 text-amber-50 transition hover:bg-amber-400/30 disabled:opacity-50"
            >
              {loading ? t('loading') : t('offlineRetry')}
            </button>
          </div>
        ) : (
          <div className="pointer-events-none fixed bottom-4 left-1/2 z-30 -translate-x-1/2 rounded-full border border-white/15 bg-slate-800/90 px-4 py-1.5 text-xs font-semibold text-white/80 shadow-lg">
            {t('offlineNotice')}
          </div>
        )
      )}
    </div>
  );
}
