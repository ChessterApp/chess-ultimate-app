'use client';

import React from 'react';
import { useTranslations } from 'next-intl';
import { BookOpen, ChevronRight, Puzzle, Swords, Target, type LucideIcon } from 'lucide-react';
import type { DailyPlan as Plan, DailyPlanCard } from '@/lib/coach/tool-summary';
import { planAction, planLayout, weakSpotView, type PlanAction } from '@/lib/coach/daily-plan';
import CoachAvatar from './CoachAvatar';

interface DailyPlanProps {
  plan: Plan;
  /** 'thread': the whole plan; 'peek' (the phone sheet's low detent): greeting, the main card, the rest as chips. */
  variant: 'thread' | 'peek';
  greetingName?: string | null;
  disabled?: boolean;
  onAction: (action: PlanAction) => void;
}

const focusRing =
  'focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-(--coach-accent)';
const pressable = `transition-colors hover:bg-white/5 active:bg-white/10 disabled:opacity-40 disabled:hover:bg-transparent ${focusRing}`;

const ICONS: Record<DailyPlanCard['type'], LucideIcon> = {
  review_last_game: Target,
  weak_spot: Puzzle,
  opening_lesson: BookOpen,
  play_coach: Swords,
};

/** A card's title and its one muted line. */
function useCardText() {
  const t = useTranslations('coach');
  return (card: DailyPlanCard): { title: string; sub?: string; chip: string } => {
    switch (card.type) {
      case 'review_last_game':
        return {
          title: t('planReviewTitle'),
          sub: card.moments_count ? `${card.title} · ${t('planReviewMoments', { count: card.moments_count })}` : card.title,
          chip: t('planReviewTitle'),
        };
      case 'weak_spot': {
        const { themeKey, stat } = weakSpotView(card);
        const theme = themeKey ? t(themeKey) : null;
        return {
          title: theme ? t('planSpotTitle', { theme }) : t('planSpotAnyTitle'),
          sub: stat ? t('planSpotStat', { found: stat.games_with, games: stat.games }) : t('planSpotPuzzles', { count: card.puzzles }),
          chip: theme ? t('planSpotChip', { theme }) : t('planSpotAnyTitle'),
        };
      }
      case 'opening_lesson':
        return { title: card.name, sub: t('planOpeningSub', { eco: card.eco }), chip: card.name };
      case 'play_coach':
        return { title: t('planPlayTitle'), sub: t('planPlaySub'), chip: t('planPlayTitle') };
    }
  };
}

function Greeting({ name, size }: { name?: string | null; size: number }) {
  const t = useTranslations('coach');
  return (
    <div className="flex items-center gap-3">
      <CoachAvatar size={size} />
      <div className="min-w-0">
        <p className="truncate text-[17px] font-semibold leading-snug text-(--coach-text)">
          {name ? t('planGreeting', { name }) : t('planGreetingAnon')}
        </p>
        <p className="text-sm text-(--coach-muted)">{t('planSubtitle')}</p>
      </div>
    </div>
  );
}

/** The plan's main card: the whole card is the button. */
function PrimaryCard({ card, compact, disabled, onTap }: { card: DailyPlanCard; compact: boolean; disabled?: boolean; onTap: () => void }) {
  const text = useCardText()(card);
  const Icon = ICONS[card.type];
  return (
    <button
      type="button"
      onClick={onTap}
      disabled={disabled}
      data-testid={`plan-${card.type}`}
      className={`flex w-full items-center gap-3 rounded-2xl border border-(--coach-accent)/50 bg-(--coach-surface-2) text-left ${compact ? 'min-h-16 p-3' : 'min-h-[76px] p-4'} ${pressable}`}
    >
      <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-(--coach-accent-soft) text-(--coach-accent-text)">
        <Icon size={22} aria-hidden />
      </span>
      <span className="min-w-0 flex-1">
        <span className="block truncate text-[16px] font-semibold text-(--coach-text)">{text.title}</span>
        {text.sub && <span className="block truncate text-[13px] text-(--coach-muted)">{text.sub}</span>}
      </span>
      <ChevronRight size={20} aria-hidden className="shrink-0 text-(--coach-accent-text)" />
    </button>
  );
}

function RowCard({ card, disabled, onTap }: { card: DailyPlanCard; disabled?: boolean; onTap: () => void }) {
  const text = useCardText()(card);
  const Icon = ICONS[card.type];
  return (
    <button
      type="button"
      onClick={onTap}
      disabled={disabled}
      data-testid={`plan-${card.type}`}
      className={`flex min-h-14 w-full items-center gap-3 rounded-xl border border-(--coach-border) bg-(--coach-surface-2) p-3 text-left ${pressable}`}
    >
      <Icon size={20} aria-hidden className="shrink-0 text-(--coach-accent-text)" />
      <span className="min-w-0 flex-1">
        <span className="block truncate text-[15px] font-medium text-(--coach-text)">{text.title}</span>
        {text.sub && <span className="block truncate text-[13px] text-(--coach-muted)">{text.sub}</span>}
      </span>
      <ChevronRight size={18} aria-hidden className="shrink-0 text-(--coach-muted)" />
    </button>
  );
}

function Tile({ card, disabled, onTap }: { card: DailyPlanCard; disabled?: boolean; onTap: () => void }) {
  const text = useCardText()(card);
  const Icon = ICONS[card.type];
  return (
    <button
      type="button"
      onClick={onTap}
      disabled={disabled}
      data-testid={`plan-${card.type}`}
      className={`flex min-h-[84px] min-w-0 flex-col items-start gap-1.5 rounded-xl border border-(--coach-border) bg-(--coach-surface-2) p-3 text-left ${pressable}`}
    >
      <Icon size={18} aria-hidden className="text-(--coach-accent-text)" />
      <span className="line-clamp-2 w-full text-[14px] font-medium leading-snug text-(--coach-text)">{text.title}</span>
      {text.sub && <span className="w-full truncate text-xs text-(--coach-muted)">{text.sub}</span>}
    </button>
  );
}

/** The coach's home on an empty session: today's plan, compact, in the coach's dark theme. */
export default function DailyPlan({ plan, variant, greetingName, disabled, onAction }: DailyPlanProps) {
  const t = useTranslations('coach');
  const text = useCardText();
  const { primary, spot, tiles } = planLayout(plan);
  const tap = (card: DailyPlanCard) => () => onAction(planAction(card, t));

  if (variant === 'peek') {
    const rest = [spot, ...tiles].filter((c): c is DailyPlanCard => c !== null);
    return (
      <div className="flex flex-col gap-2.5" data-testid="daily-plan" data-variant="peek">
        <Greeting name={greetingName} size={36} />
        <PrimaryCard card={primary} compact disabled={disabled} onTap={tap(primary)} />
        {rest.length > 0 && (
          <div className="-mx-4 flex gap-2 overflow-x-auto px-4 [scrollbar-width:none]">
            {rest.map((card) => {
              const Icon = ICONS[card.type];
              return (
                <button
                  key={card.type}
                  type="button"
                  onClick={tap(card)}
                  disabled={disabled}
                  data-testid={`plan-chip-${card.type}`}
                  className={`flex min-h-11 max-w-[220px] shrink-0 items-center gap-1.5 rounded-full border border-(--coach-border) bg-(--coach-surface-2) px-3.5 text-[13.5px] font-medium text-(--coach-text) ${pressable}`}
                >
                  <Icon size={15} aria-hidden className="shrink-0 text-(--coach-accent-text)" />
                  <span className="truncate">{text(card).chip}</span>
                </button>
              );
            })}
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="mx-auto mt-4 flex max-w-md flex-col gap-3" data-testid="daily-plan" data-variant="thread">
      <Greeting name={greetingName} size={44} />
      <PrimaryCard card={primary} compact={false} disabled={disabled} onTap={tap(primary)} />
      {spot && <RowCard card={spot} disabled={disabled} onTap={tap(spot)} />}
      {tiles.length > 0 && (
        <div className="grid grid-cols-2 gap-2">
          {tiles.map((card) => (
            <Tile key={card.type} card={card} disabled={disabled} onTap={tap(card)} />
          ))}
        </div>
      )}
      <p className="pt-1 text-center text-[13px] text-(--coach-muted)">{t('planOrAsk')}</p>
    </div>
  );
}

/** While the plan loads: the same shapes, quiet. */
export function DailyPlanSkeleton({ variant }: { variant: 'thread' | 'peek' }) {
  const t = useTranslations('coach');
  const block = 'rounded-xl bg-white/5 motion-safe:animate-pulse';
  return (
    <div
      className={variant === 'thread' ? 'mx-auto mt-4 flex max-w-md flex-col gap-3' : 'flex flex-col gap-2.5'}
      role="status"
      aria-label={t('planLoading')}
      data-testid="daily-plan-skeleton"
    >
      <div className="flex items-center gap-3">
        <CoachAvatar size={variant === 'thread' ? 44 : 36} />
        <div className="flex-1 space-y-2">
          <div className={`h-4 w-40 ${block}`} />
          <div className={`h-3 w-28 ${block}`} />
        </div>
      </div>
      <div className={`${variant === 'thread' ? 'h-[76px]' : 'h-16'} ${block} rounded-2xl`} />
      {variant === 'thread' ? (
        <>
          <div className={`h-14 ${block}`} />
          <div className="grid grid-cols-2 gap-2">
            <div className={`h-[84px] ${block}`} />
            <div className={`h-[84px] ${block}`} />
          </div>
        </>
      ) : (
        <div className="flex gap-2">
          <div className={`h-11 w-36 rounded-full ${block}`} />
          <div className={`h-11 w-32 rounded-full ${block}`} />
        </div>
      )}
    </div>
  );
}
