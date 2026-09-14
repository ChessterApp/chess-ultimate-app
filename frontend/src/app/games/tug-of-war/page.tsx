/**
 * /tug-of-war — a public, client-side classroom team-battle chess game.
 * Milestone 1: playable core (two-board puzzle race + sliding rope scene).
 * Puzzles are prefetched live from /api/puzzle at match start, with the bundled
 * TUG_PUZZLES set as an offline fallback. No auth, no backend of our own.
 */

'use client';

import { useReducer, useState } from 'react';
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

  const start = async ({ teamA, teamB, level, themes }: StartConfig) => {
    setLoading(true);
    setOffline(false);
    try {
      const { queueA, queueB, usedFallback } = await prefetchPuzzles({ level, themes });
      setOffline(usedFallback);
      dispatch({ type: 'START_MATCH', teamAName: teamA, teamBName: teamB, queueA, queueB });
    } finally {
      setLoading(false);
    }
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
        <div className="pointer-events-none fixed bottom-4 left-1/2 z-30 -translate-x-1/2 rounded-full border border-white/15 bg-slate-800/90 px-4 py-1.5 text-xs font-semibold text-white/80 shadow-lg">
          {t('offlineNotice')}
        </div>
      )}
    </div>
  );
}
