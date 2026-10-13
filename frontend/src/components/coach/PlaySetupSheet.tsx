'use client';

import React, { useEffect, useRef, useState } from 'react';
import { useTranslations } from 'next-intl';
import { X } from 'lucide-react';
import type { GameCommentMode } from '@/lib/coach/boards-api';
import { GAME_STRENGTHS, eloLevel, nearestStrengthIndex, type GameStartOptions } from '@/lib/coach/play';

const LEVEL_KEY = {
  novice: 'levelNovice',
  amateur: 'levelAmateur',
  club: 'levelClub',
  expert: 'levelExpert',
  master: 'levelMaster',
} as const;

const COMMENT_MODES: Array<{ mode: GameCommentMode; short: string; full: string }> = [
  { mode: 'quiet', short: 'commentsQuietShort', full: 'commentsQuiet' },
  { mode: 'mistakes', short: 'commentsMistakesShort', full: 'commentsMistakes' },
  { mode: 'every', short: 'commentsEveryShort', full: 'commentsEvery' },
];

interface PlaySetupSheetProps {
  /** Seeds the strength (snapped to the nearest offered one). */
  defaultElo?: number;
  /** The last game's settings, if any: the sheet opens on them. */
  initial?: GameStartOptions | null;
  busy?: boolean;
  error?: string | null;
  onStart: (options: GameStartOptions) => void;
  onCancel: () => void;
}

/**
 * "Play the coach" setup: a bottom sheet on phones, a centred card on
 * desktop. Colour, strength (named levels), how talkative the coach is.
 */
export default function PlaySetupSheet({ defaultElo = 1200, initial, busy, error, onStart, onCancel }: PlaySetupSheetProps) {
  const t = useTranslations('coach');
  const [color, setColor] = useState<GameStartOptions['color']>(initial?.color ?? 'white');
  const [eloIndex, setEloIndex] = useState(nearestStrengthIndex(initial?.elo ?? defaultElo));
  const [commentMode, setCommentMode] = useState<GameCommentMode>(initial?.comment_mode ?? 'mistakes');
  const panelRef = useRef<HTMLDivElement>(null);
  const elo = GAME_STRENGTHS[eloIndex];

  useEffect(() => {
    panelRef.current?.querySelector<HTMLElement>('[aria-checked="true"]')?.focus();
  }, []);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onCancel();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onCancel]);

  return (
    <div className="fixed inset-0 z-[60] flex items-end justify-center lg:items-center" data-testid="play-setup">
      <div className="animate-fade-in absolute inset-0 bg-black/60" onClick={onCancel} aria-hidden />
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="play-setup-title"
        className="animate-fade-in relative w-full max-w-md rounded-t-2xl border border-(--coach-border) bg-(--coach-surface) px-4 pt-2 pb-[calc(1rem+env(safe-area-inset-bottom))] shadow-2xl lg:rounded-2xl lg:pt-4 lg:pb-4"
      >
        <div className="mx-auto mb-2 h-1 w-10 rounded-full bg-white/20 lg:hidden" aria-hidden />
        <div className="flex items-center justify-between">
          <h2 id="play-setup-title" className="text-lg font-semibold text-(--coach-text)">
            {t('gameDialogTitle')}
          </h2>
          <button
            type="button"
            onClick={onCancel}
            aria-label={t('cancel')}
            className="-mr-2 flex h-11 w-11 items-center justify-center rounded-full text-(--coach-muted) hover:bg-white/5 hover:text-(--coach-text) focus-visible:outline focus-visible:outline-2 focus-visible:outline-(--coach-accent)"
          >
            <X size={20} aria-hidden />
          </button>
        </div>

        <Field label={t('gameColor')} id="setup-color">
          <Segmented
            labelledBy="setup-color"
            value={color}
            onChange={setColor}
            options={[
              { value: 'white', label: t('colorWhite') },
              { value: 'black', label: t('colorBlack') },
              { value: 'random', label: t('colorRandom') },
            ]}
          />
        </Field>

        <Field label={t('gameStrength')} id="setup-elo">
          <div className="flex items-baseline justify-between">
            <span className="text-base font-semibold text-(--coach-text)" data-testid="game-elo-level">
              {t(LEVEL_KEY[eloLevel(elo)])}
            </span>
            <span className="text-sm tabular-nums text-(--coach-muted)">{elo}</span>
          </div>
          <input
            type="range"
            min={0}
            max={GAME_STRENGTHS.length - 1}
            step={1}
            value={eloIndex}
            onChange={(e) => setEloIndex(Number(e.target.value))}
            aria-labelledby="setup-elo"
            aria-valuetext={`${elo} · ${t(LEVEL_KEY[eloLevel(elo)])}`}
            data-testid="game-elo"
            // 44px tall hit area around a thin track.
            className="mt-1 h-11 w-full cursor-pointer accent-(--coach-accent)"
          />
        </Field>

        <Field label={t('gameComments')} id="setup-comments">
          <Segmented
            labelledBy="setup-comments"
            value={commentMode}
            onChange={setCommentMode}
            options={COMMENT_MODES.map((c) => ({ value: c.mode, label: t(c.short) }))}
          />
          <p className="mt-1.5 text-xs text-(--coach-muted)">
            {t(COMMENT_MODES.find((c) => c.mode === commentMode)!.full)}
          </p>
        </Field>

        {error && (
          <p className="mt-3 text-sm text-(--coach-danger)" role="alert" data-testid="game-error">
            {error}
          </p>
        )}

        <button
          type="button"
          disabled={busy}
          onClick={() => onStart({ color, elo, comment_mode: commentMode })}
          className="mt-4 min-h-12 w-full rounded-xl bg-(--coach-accent) px-4 text-base font-semibold text-white transition hover:brightness-110 active:brightness-95 disabled:opacity-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-(--coach-accent)"
        >
          {t('startGame')}
        </button>
      </div>
    </div>
  );
}

function Field({ label, id, children }: { label: string; id: string; children: React.ReactNode }) {
  return (
    <div className="mt-4">
      <div id={id} className="mb-1.5 text-sm text-(--coach-muted)">
        {label}
      </div>
      {children}
    </div>
  );
}

function Segmented<T extends string>({
  value,
  onChange,
  options,
  labelledBy,
}: {
  value: T;
  onChange: (value: T) => void;
  options: Array<{ value: T; label: string }>;
  labelledBy: string;
}) {
  return (
    <div role="radiogroup" aria-labelledby={labelledBy} className="flex gap-1 rounded-xl bg-black/25 p-1">
      {options.map((o) => {
        const on = o.value === value;
        return (
          <button
            key={o.value}
            type="button"
            role="radio"
            aria-checked={on}
            tabIndex={on ? 0 : -1}
            onClick={() => onChange(o.value)}
            onKeyDown={(e) => {
              if (e.key !== 'ArrowRight' && e.key !== 'ArrowLeft') return;
              e.preventDefault();
              const i = options.findIndex((x) => x.value === value);
              const next = options[(i + (e.key === 'ArrowRight' ? 1 : options.length - 1)) % options.length];
              onChange(next.value);
              (e.currentTarget.parentElement?.children[options.indexOf(next)] as HTMLElement | undefined)?.focus();
            }}
            className={`min-h-11 min-w-0 flex-1 truncate rounded-lg px-2 text-sm transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-(--coach-accent) ${
              on ? 'bg-(--coach-surface-2) font-medium text-(--coach-text) shadow' : 'text-(--coach-muted) hover:text-(--coach-text)'
            }`}
          >
            {o.label}
          </button>
        );
      })}
    </div>
  );
}
