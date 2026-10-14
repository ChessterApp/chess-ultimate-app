'use client';

import React from 'react';
import { useTranslations } from 'next-intl';
import { Play } from 'lucide-react';
import { formatScore, numberedLine, type EngineLineSummary } from '@/lib/coach/tool-summary';
import { cardAction, cardShell, cardTitle } from './card-styles';

/** The eval pill: White's side, + = White better. */
export function EvalPill({ score }: { score: Parameters<typeof formatScore>[0] }) {
  return (
    <span
      className="inline-flex min-w-12 shrink-0 justify-center rounded-md bg-(--coach-accent-soft) px-2 py-0.5 text-sm font-semibold tabular-nums text-(--coach-accent-text)"
      data-testid="eval-pill"
    >
      {formatScore(score)}
    </span>
  );
}

interface EngineLineCardProps {
  summary: EngineLineSummary;
  /** «Показать на доске»: draw the best line on the board. */
  onShow?: () => void;
  disabled?: boolean;
}

/** The engine's verdict: eval pill + the best line in SAN; the other lines below, muted. */
export default function EngineLineCard({ summary, onShow, disabled }: EngineLineCardProps) {
  const t = useTranslations('coach');
  const [best, ...rest] = summary.lines;
  return (
    <section className={cardShell} data-testid="card-engine-line" aria-label={t('cardEngineTitle')}>
      <div className="flex items-baseline justify-between gap-2">
        <h3 className={cardTitle}>{t('cardEngineTitle')}</h3>
        {summary.depth && <span className="text-[11px] tabular-nums text-(--coach-muted)">{t('cardDepth', { depth: summary.depth })}</span>}
      </div>
      <div className="mt-2 flex items-start gap-2.5">
        <EvalPill score={summary} />
        <p className="min-w-0 pt-0.5 font-mono text-[14px] leading-snug text-(--coach-text) [overflow-wrap:anywhere]">
          {numberedLine(summary.fen, best.san)}
        </p>
      </div>
      {rest.map((line, i) => (
        <div key={i} className="mt-1.5 flex items-start gap-2.5 text-(--coach-muted)">
          <span className="inline-flex min-w-12 shrink-0 justify-center text-[13px] tabular-nums">{formatScore(line)}</span>
          <p className="min-w-0 font-mono text-[13px] leading-snug [overflow-wrap:anywhere]">{numberedLine(summary.fen, line.san)}</p>
        </div>
      ))}
      {onShow && (
        <div className="mt-3">
          <button type="button" onClick={onShow} disabled={disabled} className={cardAction} data-testid="card-engine-show">
            <Play size={14} aria-hidden />
            {t('cardShowOnBoard')}
          </button>
        </div>
      )}
    </section>
  );
}
