/**
 * /games/tug-of-war — a public, client-side classroom team-battle chess game.
 * Milestone 1: playable core (two-board puzzle race + sliding rope scene).
 * Each match deals 30 puzzles per team from one backend pack (real Lichess
 * puzzles) and refills both queues, excluding everything already dealt, before
 * either runs low — so nothing repeats. The bundled TUG_PUZZLES set is the
 * offline fallback when the backend is unreachable. No auth.
 */

'use client';

import { useEffect, useReducer, useRef, useState } from 'react';
import { useTranslations } from 'next-intl';
import SetupScreen, { type StartConfig } from '@/components/tug-of-war/SetupScreen';
import MatchScreen from '@/components/tug-of-war/MatchScreen';
import { gameReducer, initialState } from '@/lib/tug-of-war/gameReducer';
import { prefetchPuzzles, refillQueues, type TugLevel } from '@/lib/tug-of-war/prefetch';
import { needsRefill } from '@/lib/tug-of-war/queues';
import { track, ANALYTICS_EVENTS } from '@/lib/analytics/events';

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
  // Live-pack selection of the current match; null when playing offline.
  const live = useRef<{ level: TugLevel; themes: string[] } | null>(null);
  // Bumped per start so a late refill never lands in a newer match.
  const matchId = useRef(0);
  const refilling = useRef(false);
  // The selection has no unseen puzzles left; stop asking.
  const exhausted = useRef(false);

  const start = async (config: StartConfig) => {
    const { teamA, teamB, level, themes } = config;
    lastConfig.current = config;
    matchId.current += 1;
    live.current = null;
    refilling.current = false;
    exhausted.current = false;
    setLoading(true);
    setOffline(false);
    setThemesUnavailable(false);
    try {
      const { queueA, queueB, usedFallback, themesUnavailable: themesMissing } =
        await prefetchPuzzles({ level, themes });
      if (!usedFallback) live.current = { level, themes };
      setOffline(usedFallback);
      setThemesUnavailable(themesMissing);
      dispatch({ type: 'START_MATCH', teamAName: teamA, teamBName: teamB, queueA, queueB });
      track(ANALYTICS_EVENTS.TUG_OF_WAR_STARTED, { level });
    } finally {
      setLoading(false);
    }
  };

  // Refill both queues before either team runs out, excluding every puzzle
  // already dealt this match. A failed refill retries on the next board change.
  const { phase, boardA, boardB } = state;
  useEffect(() => {
    if (phase !== 'match' || !live.current || refilling.current || exhausted.current) return;
    if (!needsRefill([boardA, boardB])) return;
    const id = matchId.current;
    refilling.current = true;
    const exclude = [...boardA.puzzles, ...boardB.puzzles].map((p) => p.id);
    void refillQueues({ ...live.current, exclude })
      .then((deltas) => {
        if (id !== matchId.current || !deltas) return;
        if (deltas.queueA.length + deltas.queueB.length === 0) exhausted.current = true;
        else dispatch({ type: 'APPEND_PUZZLES', queueA: deltas.queueA, queueB: deltas.queueB });
      })
      .finally(() => {
        if (id === matchId.current) refilling.current = false;
      });
  }, [phase, boardA, boardB]);

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
