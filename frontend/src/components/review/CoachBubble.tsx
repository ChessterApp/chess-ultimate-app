'use client';

import { useLocale, useTranslations } from 'next-intl';
import ClassificationIcon from './ClassificationIcon';
import type { ReviewMove } from './types';
import type { CoachEntry } from '@/hooks/useReviewCoach';
import { translateOpeningName } from '@/lib/openings/openingNamesI18n';

/** Minimal shape of the `gameReview` translator used by {@link coachText}. */
type CoachTranslate = (key: string, values?: Record<string, string | number>) => string;

/**
 * Signed eval delta of a move in PAWNS, from the MOVER's point of view.
 * Positive = the move improved the mover's eval; negative = it cost them.
 * Book plies and ply 1 have no meaningful "before", so we compare against the
 * previous position's white-POV eval (0 before the first move).
 */
export function evalDeltaPawns(move: ReviewMove, prev: ReviewMove | null): number {
  const before = prev ? evalToCp(prev) : 0;
  const after = evalToCp(move);
  const whiteDelta = after - before;
  const moverIsWhite = move.ply % 2 === 1;
  const moverDelta = moverIsWhite ? whiteDelta : -whiteDelta;
  return moverDelta / 100;
}

/** White-POV centipawns, mate resolved to a large clamp so deltas stay finite. */
function evalToCp(move: ReviewMove): number {
  if (move.eval.type === 'mate') {
    return move.eval.value >= 0 ? 2000 : -2000;
  }
  return move.eval.value;
}

/** "+1.2" / "-0.4" / "0.0" — always signed. */
export function formatDelta(pawns: number): string {
  const rounded = Math.abs(pawns) < 0.05 ? 0 : pawns;
  const sign = rounded > 0 ? '+' : rounded < 0 ? '−' : '';
  return `${sign}${Math.abs(rounded).toFixed(1)}`;
}

/**
 * Deterministic v1 coach commentary — a template per classification, keyed on
 * SAN, book/opening flag and a trivially-derivable "hangs a piece" hint (a
 * capture SAN answering a blunder/mistake). Templates resolve at render time
 * from the `gameReview` catalog via `t`, so they follow the active locale. The
 * LLM "Explain" upgrade is Phase 5.
 */
export function coachText(
  t: CoachTranslate,
  move: ReviewMove,
  prev: ReviewMove | null,
  opening?: { name?: string; lastBookPly?: number },
): string {
  const san = move.san;
  const isLastBook = !!opening && opening.lastBookPly === move.ply;

  switch (move.classification) {
    case 'book':
      if (isLastBook) {
        return opening?.name
          ? t('coach.moveComments.bookLast', { san, opening: opening.name })
          : t('coach.moveComments.bookLastNoName', { san });
      }
      return t('coach.moveComments.bookTheory', { san });
    case 'brilliant':
      return t('coach.moveComments.brilliant', { san });
    case 'great':
      return t('coach.moveComments.great', { san });
    case 'best':
      return t('coach.moveComments.best', { san });
    case 'excellent':
      return t('coach.moveComments.excellent', { san });
    case 'good':
      return t('coach.moveComments.good', { san });
    case 'forced':
      return t('coach.moveComments.forced', { san });
    case 'inaccuracy':
      return t('coach.moveComments.inaccuracy', { san });
    case 'mistake':
      return t('coach.moveComments.mistake', { san });
    case 'miss':
      return t('coach.moveComments.miss', { san });
    case 'blunder':
      return dropsMaterial(move, prev)
        ? t('coach.moveComments.blunderDropsMaterial', { san })
        : t('coach.moveComments.blunder', { san });
    default:
      return san;
  }
}

/** A blunder/mistake whose eval collapsed alongside a capture-shaped reply. */
function dropsMaterial(move: ReviewMove, prev: ReviewMove | null): boolean {
  const delta = evalDeltaPawns(move, prev);
  return delta <= -2;
}

export interface CoachBubbleProps {
  move: ReviewMove | null;
  prev: ReviewMove | null;
  opening?: { name?: string; lastBookPly?: number };
  /**
   * Review Coach v1 (F1). The LLM "Explain" state for the current move and a
   * trigger to start it. Purely additive — omit both and the bubble renders
   * exactly as before (deterministic template only).
   */
  coach?: CoachEntry;
  onExplain?: () => void;
}

/** Review-mode coach bubble: classification icon + SAN + delta chip + text. */
export default function CoachBubble({ move, prev, opening, coach, onExplain }: CoachBubbleProps) {
  const t = useTranslations('gameReview');
  const locale = useLocale();
  if (!move) {
    return (
      <div className="review-card" data-testid="coach-bubble" style={{ padding: 14, minHeight: 92 }}>
        <p style={{ fontSize: 13, opacity: 0.75, margin: 0 }}>
          {t('coach.bubblePlaceholder')}
        </p>
      </div>
    );
  }

  const delta = evalDeltaPawns(move, prev);
  const deltaStr = formatDelta(delta);
  const deltaNegative = delta < -0.05;
  // Display-only: the raw (English) name still goes to the coach via onExplain.
  const shownOpening = opening?.name
    ? { ...opening, name: translateOpeningName(opening.name, locale) }
    : opening;

  return (
    <div
      className="review-card"
      data-testid="coach-bubble"
      data-classification={move.classification}
      style={{ padding: 14, minHeight: 92, display: 'flex', gap: 12, alignItems: 'flex-start' }}
    >
      <div style={{ width: 40, height: 40, flex: 'none' }}>
        <ClassificationIcon type={move.classification} />
      </div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap', marginBottom: 4 }}>
          <span
            className="review-heading"
            data-testid="coach-san"
            style={{
              fontWeight: 800,
              fontSize: 15,
              color: `var(--color-classification-${move.classification})`,
            }}
          >
            {move.san}
          </span>
          <span style={{ fontSize: 12, fontWeight: 700, opacity: 0.7 }}>
            {t(`classifications.${move.classification}`)}
          </span>
          <span
            data-testid="coach-delta"
            style={{
              fontSize: 12,
              fontWeight: 800,
              padding: '1px 7px',
              borderRadius: 999,
              background: 'var(--review-neutral)',
              color: deltaNegative ? 'var(--color-classification-blunder)' : 'var(--review-text-dim)',
            }}
          >
            {deltaStr}
          </span>
        </div>
        <p style={{ fontSize: 13, lineHeight: 1.4, margin: 0, opacity: 0.9 }}>
          {coachText(t, move, prev, shownOpening)}
        </p>
        {shownOpening?.name && move.classification === 'book' && (
          <div
            style={{ fontSize: 11.5, marginTop: 6, opacity: 0.6, textDecoration: 'underline' }}
          >
            {shownOpening.name}
          </div>
        )}
        {onExplain && <ExplainSection t={t} coach={coach} onExplain={onExplain} />}
      </div>
    </div>
  );
}

/** F1 per-move LLM Explain: manual trigger, streamed tokens, loading + error. */
function ExplainSection({
  t,
  coach,
  onExplain,
}: {
  t: ReturnType<typeof useTranslations>;
  coach?: CoachEntry;
  onExplain: () => void;
}) {
  const status = coach?.status ?? 'idle';
  const content = coach?.content ?? '';
  const streaming = status === 'streaming';

  // Idle with nothing yet → show the trigger button.
  if (status === 'idle') {
    return (
      <button
        type="button"
        data-testid="coach-explain-btn"
        onClick={onExplain}
        className="review-ghost-btn"
        style={{ marginTop: 10, padding: '6px 12px', fontSize: 12.5, fontWeight: 700 }}
      >
        ✨ {t('coach.explain.cta')}
      </button>
    );
  }

  if (status === 'error') {
    return (
      <div style={{ marginTop: 10 }}>
        <p
          data-testid="coach-explain-error"
          style={{ fontSize: 12.5, margin: '0 0 6px', color: 'var(--color-classification-blunder)' }}
        >
          {t('coach.explain.error')}
        </p>
        <button
          type="button"
          data-testid="coach-explain-retry"
          onClick={onExplain}
          className="review-ghost-btn"
          style={{ padding: '6px 12px', fontSize: 12.5, fontWeight: 700 }}
        >
          {t('coach.explain.retry')}
        </button>
      </div>
    );
  }

  // streaming or done → render whatever text we have so far.
  return (
    <div
      data-testid="coach-explain-content"
      style={{
        marginTop: 10,
        paddingTop: 10,
        borderTop: '1px solid var(--review-border, rgba(255,255,255,0.08))',
        fontSize: 12.5,
        lineHeight: 1.5,
        whiteSpace: 'pre-wrap',
      }}
    >
      {content}
      {streaming && (
        <span data-testid="coach-explain-loading" style={{ opacity: 0.6 }}>
          {content ? ' ▍' : t('coach.explain.loading')}
        </span>
      )}
    </div>
  );
}
