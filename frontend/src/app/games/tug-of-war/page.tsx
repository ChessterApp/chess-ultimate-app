/**
 * /games/tug-of-war — a public, client-side classroom team-battle chess game.
 * Milestone 1: playable core (two-board puzzle race + sliding rope scene).
 * Each match deals 30 puzzles per team from one backend pack (real Lichess
 * puzzles) and refills both queues, excluding everything already dealt, before
 * either runs low — so nothing repeats. The bundled TUG_PUZZLES set is the
 * offline fallback when the backend is unreachable. No auth.
 * Modes: Team vs Team (two humans) or You vs Chesster (side B is a zebra bot;
 * both sides draw puzzles within ±150 of the bot's rating — or, in Adaptive
 * mode, from small rating-targeted batches that follow the player).
 */

'use client';

import { useEffect, useReducer, useRef, useState } from 'react';
import { useTranslations } from 'next-intl';
import SetupScreen, { type StartConfig } from '@/components/tug-of-war/SetupScreen';
import MatchScreen from '@/components/tug-of-war/MatchScreen';
import { gameReducer, initialState } from '@/lib/tug-of-war/gameReducer';
import {
  prefetchAdaptive,
  prefetchBot,
  prefetchPuzzles,
  refillAdaptive,
  refillBot,
  refillQueues,
  ADAPTIVE_REFILL_THRESHOLD,
  type TugLevel,
} from '@/lib/tug-of-war/prefetch';
import { needsRefill } from '@/lib/tug-of-war/queues';
import { track, ANALYTICS_EVENTS } from '@/lib/analytics/events';
import { botLevel, type BotLevelId } from '@/lib/tug-of-war/bot';
import { initialAdaptive, loadAdaptive, targetRating } from '@/lib/tug-of-war/adaptive';
import { useAdaptiveBot, type AdaptiveSession } from '@/lib/tug-of-war/useAdaptiveBot';

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
  // Zebra rank of the current (or last) You vs Chesster match; null = teams.
  const [bot, setBot] = useState<BotLevelId | null>(null);
  // Set while an Adaptive match (or its end screen) is on.
  const [session, setSession] = useState<AdaptiveSession | null>(null);
  // Remounts the match screen per start (an adaptive rematch starts from the end screen).
  const [matchKey, setMatchKey] = useState(0);
  // Remember the last setup so the "retry live fetch" button can re-run it.
  const lastConfig = useRef<StartConfig | null>(null);
  // Live-pack selection of the current match; null when playing offline.
  const live = useRef<{ level: TugLevel; themes: string[] } | { rating: number } | 'adaptive' | null>(null);
  // Bumped per start so a late refill never lands in a newer match.
  const matchId = useRef(0);
  const refilling = useRef(false);
  // The selection has no unseen puzzles left; stop asking.
  const exhausted = useRef(false);

  const start = async (config: StartConfig) => {
    const { teamA, teamB, level, themes, bot: botId = null, adaptive = false } = config;
    lastConfig.current = config;
    matchId.current += 1;
    live.current = null;
    refilling.current = false;
    exhausted.current = false;
    setLoading(true);
    setOffline(false);
    setThemesUnavailable(false);
    try {
      // Adaptive: start from the saved estimate (a rematch picks up where the last match ended).
      const next: AdaptiveSession | null = adaptive ? { saved: loadAdaptive() } : null;
      const seed = next && initialAdaptive(next.saved);
      const rating = botId ? botLevel(botId).rating : null;
      const { queueA, queueB, usedFallback, themesUnavailable: themesMissing } = seed
        ? await prefetchAdaptive({ rating: targetRating(seed) })
        : rating !== null
          ? await prefetchBot({ rating })
          : await prefetchPuzzles({ level, themes });
      if (!usedFallback) live.current = next ? 'adaptive' : rating !== null ? { rating } : { level, themes };
      setOffline(usedFallback);
      setThemesUnavailable(themesMissing);
      setBot(botId);
      setSession(next);
      setMatchKey((k) => k + 1);
      dispatch({ type: 'START_MATCH', teamAName: teamA, teamBName: teamB, queueA, queueB });
      track(
        ANALYTICS_EVENTS.TUG_OF_WAR_STARTED,
        seed
          ? { mode: 'bot', botMode: 'adaptive', estimate: Math.round(seed.player.estimate) }
          : botId
            ? { mode: 'bot', botMode: 'static', botLevel: botId }
            : { level },
      );
    } finally {
      setLoading(false);
    }
  };

  // Refill both queues before either team runs out, excluding every puzzle
  // already dealt this match. A failed refill retries on the next board change.
  // Adaptive matches top up in small batches around the current target.
  const { phase, boardA, boardB } = state;
  const adaptive = useAdaptiveBot(session, state);
  const target = adaptive?.target ?? null;
  useEffect(() => {
    const selection = live.current;
    if (phase !== 'match' || !selection || refilling.current || exhausted.current) return;
    const isAdaptive = selection === 'adaptive';
    if (!needsRefill([boardA, boardB], isAdaptive ? ADAPTIVE_REFILL_THRESHOLD : undefined)) return;
    const id = matchId.current;
    refilling.current = true;
    const exclude = [...boardA.puzzles, ...boardB.puzzles].map((p) => p.id);
    const refill = isAdaptive
      ? refillAdaptive({ rating: target ?? 0, exclude })
      : 'rating' in selection
        ? refillBot({ rating: selection.rating, exclude })
        : refillQueues({ ...selection, exclude });
    void refill
      .then((deltas) => {
        if (id !== matchId.current || !deltas) return;
        if (deltas.queueA.length + deltas.queueB.length === 0) exhausted.current = true;
        else dispatch({ type: 'APPEND_PUZZLES', queueA: deltas.queueA, queueB: deltas.queueB });
      })
      .finally(() => {
        if (id === matchId.current) refilling.current = false;
      });
  }, [phase, boardA, boardB, target]);

  const retryLiveFetch = () => {
    if (lastConfig.current) void start(lastConfig.current);
  };

  // Adaptive Rematch starts straight away from the just-saved estimate.
  const rematchAdaptive = () => {
    if (!loading) retryLiveFetch();
  };

  // Adaptive end screen → setup in You vs Chesster, the reached rank preselected.
  const tryFixed = () => {
    if (adaptive) setBot(adaptive.bot.id);
    setSession(null);
    dispatch({ type: 'REMATCH' });
  };

  return (
    <div className="relative min-h-screen bg-gradient-to-b from-slate-950 via-slate-900 to-slate-950">
      {state.phase === 'setup' ? (
        <SetupScreen
          initialTeamA={state.teamAName}
          initialTeamB={state.teamBName}
          onStart={start}
          loading={loading}
          initialBot={bot}
        />
      ) : (
        <MatchScreen
          key={matchKey}
          state={state}
          dispatch={dispatch}
          bot={adaptive ? adaptive.bot : bot ? botLevel(bot) : undefined}
          adaptive={adaptive ?? undefined}
          onRematch={adaptive ? rematchAdaptive : undefined}
          onTryFixed={tryFixed}
        />
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
