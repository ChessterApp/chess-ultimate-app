'use client';

import React from 'react';
import { useTranslations } from 'next-intl';
import { GraduationCap } from 'lucide-react';
import { numberedLine, type OpeningSummary } from '@/lib/coach/tool-summary';
import { cardAction, cardShell } from './card-styles';

const START_FEN = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1';

interface OpeningCardProps {
  summary: OpeningSummary;
  /** «Учить линию»: asks the coach to teach the line. */
  onLearn?: () => void;
  disabled?: boolean;
}

/** Name, ECO, the book line and master results as a white / draw / black bar. */
export default function OpeningCard({ summary, onLearn, disabled }: OpeningCardProps) {
  const t = useTranslations('coach');
  const { stats } = summary;
  const segments = stats
    ? [
        { key: 'white', pct: stats.white, label: t('cardWhiteWins'), bar: 'bg-(--coach-text)' },
        { key: 'draw', pct: stats.draw, label: t('cardDraws'), bar: 'bg-(--coach-muted)' },
        { key: 'black', pct: stats.black, label: t('cardBlackWins'), bar: 'bg-(--coach-bg)' },
      ]
    : [];
  return (
    <section className={cardShell} data-testid="card-opening" aria-label={summary.name}>
      <div className="flex items-start justify-between gap-3">
        <h3 className="min-w-0 text-[15px] font-semibold leading-snug [overflow-wrap:anywhere]">{summary.name}</h3>
        <span className="shrink-0 rounded-md border border-(--coach-border) px-1.5 py-0.5 font-mono text-[12px] text-(--coach-muted)">
          {summary.eco}
        </span>
      </div>
      {summary.moves_san && (
        <p className="mt-1 font-mono text-[13px] leading-snug text-(--coach-muted) [overflow-wrap:anywhere]">
          {numberedLine(START_FEN, summary.moves_san)}
        </p>
      )}
      {stats && (
        <div className="mt-3">
          <div className="flex h-2.5 overflow-hidden rounded-full border border-(--coach-border)" data-testid="opening-wdl" aria-hidden>
            {segments.map((s) => (
              <span key={s.key} className={s.bar} style={{ width: `${s.pct}%` }} />
            ))}
          </div>
          <dl className="mt-1.5 flex justify-between gap-2 text-[12px] tabular-nums text-(--coach-muted)">
            {segments.map((s) => (
              <div key={s.key} className="flex gap-1">
                <dt>{s.label}</dt>
                <dd className="font-semibold text-(--coach-text)">{Math.round(s.pct)}%</dd>
              </div>
            ))}
          </dl>
          <p className="mt-1 text-[12px] text-(--coach-muted)">{t('cardGamesCount', { count: stats.games })}</p>
        </div>
      )}
      {onLearn && (
        <div className="mt-3">
          <button type="button" onClick={onLearn} disabled={disabled} className={cardAction} data-testid="card-opening-learn">
            <GraduationCap size={15} aria-hidden />
            {t('cardOpeningLearn')}
          </button>
        </div>
      )}
    </section>
  );
}
