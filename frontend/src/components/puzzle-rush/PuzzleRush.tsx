'use client';

import { useCallback, useEffect, useState } from 'react';
import Image from 'next/image';
import Link from 'next/link';
import { useTranslations } from 'next-intl';
import { useAuth } from '@clerk/nextjs';
import { usePuzzleRush } from '@/hooks/usePuzzleRush';
import { rushApi } from '@/lib/puzzle-rush/api';
import { STARTING_FEN } from '@/lib/puzzle-rush/runReducer';
import { hasSeenRules, loadGuestBests, loadLastMode, markRulesSeen, DEFAULT_MODE } from '@/lib/puzzle-rush/storage';
import type { BestsResponse, RushMode } from '@/lib/puzzle-rush/types';
import { fraunces } from './fonts';
import ModeSelect from './ModeSelect';
import RulesModal from './RulesModal';
import ResultsModal from './ResultsModal';
import Leaderboard from './Leaderboard';
import RunSummary, { useRunReview } from './RunSummary';
import RushBoard from './RushBoard';
import { CoachToast, LOGO_SRC, ResultsGrid, ScoreTile, StrikesTile, TimerTile } from './RunTiles';
import styles from './PuzzleRush.module.css';

const SIGN_IN_HREF = '/sign-in?redirect_url=/games/puzzlerush';
const CONFETTI_COLORS = ['#14b8a6', '#0d9488', '#2dd4bf', '#f59e0b', '#ffffff'];

async function firePbConfetti() {
  const confetti = (await import('canvas-confetti')).default;
  confetti({ particleCount: 90, spread: 80, startVelocity: 42, origin: { x: 0.5, y: 0.55 }, colors: CONFETTI_COLORS, zIndex: 1400 });
}

function Brand({ compact = false }: { compact?: boolean }) {
  const t = useTranslations('puzzleRush');
  return (
    <div className={styles.brand}>
      <span className={styles.mark}>
        <Image src={LOGO_SRC} alt="Chesster" width={46} height={46} unoptimized priority />
      </span>
      <div>
        <h1 className={styles.brandTitle}>{t('title')}</h1>
        {!compact && <p className={styles.brandSub}>{t('subtitle')}</p>}
      </div>
    </div>
  );
}

export default function PuzzleRush() {
  const t = useTranslations('puzzleRush');
  const { userId } = useAuth();
  const [mode, setMode] = useState<RushMode>(DEFAULT_MODE);
  const [tab, setTab] = useState<'play' | 'leaderboard'>('play');
  const [rulesOpen, setRulesOpen] = useState(false);
  const [bests, setBests] = useState<BestsResponse | null>(null);

  const rush = usePuzzleRush(DEFAULT_MODE);
  const { state, tiles, countdown, showResults, closeResults, isPb, isGuest, auth } = rush;
  const review = useRunReview(state.phase === 'over' ? state.runId : null, rush.review);

  // localStorage-backed choices only after mount (SSR renders the defaults, so
  // reading them during render would cause a hydration mismatch).
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- post-hydration sync from localStorage
    setMode(loadLastMode());
    if (!hasSeenRules()) setRulesOpen(true);
  }, []);

  const runOver = state.phase === 'over';
  // Refetch bests / boards once each finished run has been recorded.
  const finishedRun = rush.recorded ? state.runId ?? '' : '';

  useEffect(() => {
    let live = true;
    const load = isGuest ? Promise.resolve(loadGuestBests()) : rushApi.bests(auth());
    load
      .then((b) => { if (live) setBests(b); })
      .catch(() => { if (live) setBests(null); });
    return () => { live = false; };
  }, [isGuest, auth, finishedRun]);

  useEffect(() => {
    if (showResults && isPb) void firePbConfetti();
  }, [showResults, isPb]);

  const closeRules = useCallback(() => {
    markRulesSeen();
    setRulesOpen(false);
  }, []);

  const startRun = useCallback((m: RushMode) => {
    setMode(m);
    setTab('play');
    void rush.start(m);
  }, [rush]);

  const playAgain = useCallback(() => startRun(state.mode), [startRun, state.mode]);
  const newRush = useCallback(() => {
    setMode(state.mode);
    rush.reset();
  }, [rush, state.mode]);

  const inRun = state.phase === 'starting' || state.phase === 'countdown' || state.phase === 'playing';
  const turnSide = state.puzzle?.color;

  const turnLine = turnSide ? (
    <p className={styles.turn} data-testid="rush-turn">
      <b>{t(`run.${turnSide}`)}</b> {t('run.toMove')} · {t('run.rating', { rating: state.puzzle!.rating })}
    </p>
  ) : <p className={styles.turn} aria-hidden="true" />;

  const coachText = state.coach ? t(`coach.${state.coach.cue}`) : null;

  const tabs = (
    <div className={styles.tabs} role="tablist">
      {(['play', 'leaderboard'] as const).map((k) => (
        <button
          key={k}
          type="button"
          role="tab"
          aria-selected={tab === k}
          className={`${styles.tab} ${tab === k ? styles.tabActive : ''}`}
          onClick={() => setTab(k)}
        >
          {k === 'play' && runOver ? t('run.results') : t(`tabs.${k}`)}
        </button>
      ))}
    </div>
  );

  const leaderboard = (
    <Leaderboard
      mode={runOver ? state.mode : mode}
      auth={auth}
      isGuest={isGuest}
      userId={userId ?? null}
      signInHref={SIGN_IN_HREF}
      refreshKey={finishedRun}
    />
  );

  let body: React.ReactNode;
  // The frozen run board stays under the results modal: swapping to the
  // summary layout (a fresh board) in the run-ending frame would delay the
  // final ✕ and the modal. The summary takes over once the modal closes.
  if (inRun || (runOver && showResults)) {
    // S3–S7: countdown and the run itself.
    body = (
      <div className={styles.runLayout}>
        <div className={styles.runBoard}>
          <RushBoard
            fen={state.fen}
            orientation={state.orientation}
            boardKey={state.boardKey}
            lastMove={state.lastMove}
            movable={state.phase === 'playing' && !state.inputLocked}
            covered={state.covered}
            waiting={state.stalled}
            badge={state.badge}
            countdown={countdown}
            goLabel={t('run.go')}
            onMove={rush.onMove}
          />
          {turnLine}
        </div>
        <div className={styles.runTiles}>
          <ScoreTile score={state.score} />
          <TimerTile
            mode={state.mode}
            startedAtMs={state.startedAtMs}
            deadlineMs={state.deadlineMs}
            running={state.phase === 'playing' || state.phase === 'countdown'}
          />
          <StrikesTile strikes={state.strikes} />
        </div>
        <div className={styles.runExtras}>
          <ResultsGrid tiles={tiles} />
          {coachText && <CoachToast key={state.coach!.seq} text={coachText} />}
          <div className={styles.quitRow}>
            <button type="button" className={styles.textButton} onClick={rush.quit} disabled={state.phase !== 'playing'}>
              ⚑ {t('run.quit')}
            </button>
          </div>
        </div>
      </div>
    );
  } else if (runOver) {
    // S8 / S10: frozen board (or the puzzle under review) + summary.
    const rb = review.board;
    body = (
      <div className={styles.layout}>
        <div className={styles.boardCol}>
          <RushBoard
            fen={rb?.fen ?? state.fen}
            orientation={rb?.orientation ?? state.orientation}
            boardKey={state.boardKey * 1000 + (review.selected ?? -1) + 1}
            lastMove={rb ? rb.lastMove : state.lastMove}
            movable={false}
            badge={rb ? null : state.badge}
          />
          {rb ? <p className={styles.turn} aria-hidden="true" /> : turnLine}
        </div>
        <section className={styles.panel}>
          <Brand compact />
          {tabs}
          {tab === 'play' ? (
            <RunSummary
              mode={state.mode}
              score={state.score}
              tiles={tiles}
              endReason={state.endReason}
              review={review}
              onPlayAgain={playAgain}
              onNewRush={newRush}
            />
          ) : leaderboard}
        </section>
      </div>
    );
  } else {
    // S1: mode select.
    body = (
      <div className={styles.layout}>
        <div className={`${styles.boardCol} ${styles.hideOnMobile}`}>
          <RushBoard fen={STARTING_FEN} orientation="white" boardKey={state.boardKey} lastMove={null} movable={false} />
        </div>
        <section className={styles.panel}>
          <Brand />
          {tabs}
          {tab === 'play' ? (
            <>
              <ModeSelect selected={mode} bests={bests} onSelect={setMode} />
              <button type="button" className={styles.cta} onClick={() => startRun(mode)}>
                {t('start')} →
              </button>
              {state.error && (
                <p className={styles.errorNote} role="alert">
                  {t('errors.start')}
                </p>
              )}
              <div className={styles.guestNote}>
                {isGuest && (
                  <>
                    <span>{t('guest.note')}</span>
                    <a className={styles.linkButton} href={SIGN_IN_HREF}>{t('guest.signIn')}</a>
                  </>
                )}
                <button type="button" className={styles.linkButton} onClick={() => setRulesOpen(true)}>
                  {t('howItWorks')}
                </button>
              </div>
            </>
          ) : leaderboard}
        </section>
      </div>
    );
  }

  return (
    <div className={`${styles.root} ${fraunces.variable}`}>
      <div className={styles.shell}>
        {!inRun && (
          <Link href="/puzzle" className={styles.backLink}>← {t('back')}</Link>
        )}
        {body}
      </div>
      {rulesOpen && !inRun && <RulesModal onClose={closeRules} />}
      {showResults && runOver && (
        <ResultsModal
          mode={state.mode}
          score={state.score}
          results={state.results}
          endReason={state.endReason}
          isPb={isPb}
          isGuest={isGuest}
          guestBests={rush.guestBest}
          ranksPending={rush.ranksPending}
          onPlayAgain={playAgain}
          onNewRush={newRush}
          onClose={closeResults}
          signInHref={SIGN_IN_HREF}
        />
      )}
    </div>
  );
}
