'use client';

import { Suspense, useCallback, useEffect, useState } from 'react';
import { useParams, useSearchParams } from 'next/navigation';
import { useTranslations } from 'next-intl';
import { useDarkMode } from '@/hooks/useDarkMode';
import {
  ReviewBoard,
  ReviewProgress,
  ReviewSidebar,
  EvalBar,
  EvalGraph,
  PlaybackControls,
  useReviewStore,
  fetchReview,
  ReviewFetchError,
} from '@/components/review';
import type { EngineEval } from '@/components/review';
import type { CoachArrow } from '@/lib/coach/review-markup';

const START_FEN = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1';
const POLL_MS = 1500;

export default function ReviewPage() {
  // useSearchParams requires a Suspense boundary during prerender.
  return (
    <Suspense fallback={null}>
      <ReviewPageInner />
    </Suspense>
  );
}

function ReviewPageInner() {
  const t = useTranslations('gameReview');
  const params = useParams<{ id: string }>();
  const search = useSearchParams();
  const id = params?.id ?? '';
  const orientation = (search?.get('orientation') as 'white' | 'black') || 'white';

  const { isDark, toggle } = useDarkMode();
  const { state, dispatch } = useReviewStore(id);
  const { data, currentPly, mode } = state;

  // Board's real rendered pixel size, reported by ReviewBoard. Drives the eval
  // bar height from one measured value so the bar matches the board exactly.
  const [boardPx, setBoardPx] = useState<number | undefined>(undefined);
  const [coachShapes, setCoachShapes] = useState<{ arrows: CoachArrow[]; squares: string[] }>({
    arrows: [],
    squares: [],
  });
  const handleCoachShapes = useCallback(
    (arrows: CoachArrow[], squares: string[]) => setCoachShapes({ arrows, squares }),
    [],
  );

  // Poll the backend until the analysis is done (or errors).
  const done = data != null;
  const [progress, setProgressVal] = useState(0);
  const [status, setStatus] = useState<'queued' | 'running' | 'done' | 'error'>('queued');

  useEffect(() => {
    if (!id || done) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;

    const poll = async () => {
      try {
        const job = await fetchReview(id);
        if (cancelled) return;
        setStatus(job.status);
        setProgressVal(job.progress ?? 0);
        if (job.status === 'done' && job.result) {
          dispatch({ type: 'setData', data: job.result });
          dispatch({ type: 'setPly', ply: job.result.moves.length });
          return;
        }
        if (job.status === 'error') return;
        timer = setTimeout(poll, POLL_MS);
      } catch (err) {
        if (cancelled) return;
        // A 4xx (notably 404 = unknown id) is terminal — the backend sidecar
        // means an in-flight job now reports queued/running, so a 404 is a real
        // "not found", not a transient cross-worker miss. Stop polling and show
        // the error instead of looping forever. Retry only network/5xx blips.
        const httpStatus = err instanceof ReviewFetchError ? err.status : 0;
        if (httpStatus >= 400 && httpStatus < 500) {
          setStatus('error');
          return;
        }
        timer = setTimeout(poll, POLL_MS);
      }
    };
    poll();
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [id, done, dispatch, setProgressVal, setStatus]);

  // Keyboard navigation ←/→ once loaded.
  useEffect(() => {
    if (!data) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'ArrowLeft') dispatch({ type: 'stepPly', delta: -1 });
      if (e.key === 'ArrowRight') dispatch({ type: 'stepPly', delta: 1 });
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [data, dispatch]);

  const themeAttr = isDark ? 'dark' : 'light';

  const currentMove = data && currentPly >= 1 ? data.moves[currentPly - 1] : null;
  const fen = currentMove?.fen ?? START_FEN;
  const whiteWin = currentMove?.winPercent ?? 50;
  const evaluation: EngineEval = currentMove?.eval ?? { type: 'cp', value: 0 };

  return (
    <div className="review-root" data-theme={themeAttr}>
      <header className="review-topbar">
        <div
          className="review-heading"
          style={{ fontSize: 19, fontWeight: 800, color: 'var(--review-accent)' }}
        >
          ♞ Chesster{' '}
          <span style={{ color: 'var(--review-text-dim)', fontWeight: 600 }}>
            · {t('header.subtitle')}
          </span>
        </div>
        <button
          type="button"
          onClick={toggle}
          className="review-ghost-btn"
          style={{ padding: '6px 12px', fontSize: 13 }}
          aria-label={t('header.toggleTheme')}
        >
          {isDark ? t('header.dark') : t('header.light')}
        </button>
      </header>

      {!data ? (
        status === 'error' ? (
          <div style={{ textAlign: 'center', padding: 48 }}>
            <div className="review-heading" style={{ fontSize: 20, fontWeight: 800 }}>
              {t('header.failedTitle')}
            </div>
            <p style={{ opacity: 0.7, marginTop: 8 }}>{t('header.failedBody')}</p>
          </div>
        ) : (
          <ReviewProgress progress={progress} status={status === 'running' ? 'running' : 'queued'} />
        )
      ) : (
        <main className="review-main">
          <section className="review-board-col">
            <div className="review-board-row">
              <EvalBar whiteWinPercent={whiteWin} evaluation={evaluation} height={boardPx} />
              <ReviewBoard
                fen={fen}
                orientation={orientation}
                move={currentMove}
                animationKey={currentPly}
                onBoardSize={setBoardPx}
                coachArrows={coachShapes.arrows}
                coachSquares={coachShapes.squares}
              />
            </div>
            {/* Replay bar glued directly under the board (both modes) so it's
                reachable by thumb on mobile instead of buried in the sidebar. */}
            <PlaybackControls
              currentPly={currentPly}
              maxPly={data.moves.length}
              keyMoments={data.keyMoments}
              onJump={(ply) => dispatch({ type: 'setPly', ply })}
              onStep={(delta) => dispatch({ type: 'stepPly', delta })}
            />
          </section>

          <div className="review-side-col">
            <ReviewSidebar
              data={data}
              mode={mode}
              white={{ name: t('players.white'), rating: data.estRating.w }}
              black={{ name: t('players.black'), rating: data.estRating.b }}
              onStartReview={() => dispatch({ type: 'setMode', mode: 'review' })}
              currentPly={currentPly}
              onSetPly={(ply) => dispatch({ type: 'setPly', ply })}
              onExitReview={() => dispatch({ type: 'setMode', mode: 'highlights' })}
              onCoachShapes={handleCoachShapes}
            />
            <EvalGraph
              moves={data.moves}
              keyMoments={data.keyMoments}
              currentPly={currentPly}
              onSelectPly={(ply) => dispatch({ type: 'setPly', ply })}
            />
          </div>
        </main>
      )}
    </div>
  );
}
