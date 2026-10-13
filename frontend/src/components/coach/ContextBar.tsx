'use client';

import React, { useEffect, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import { useTranslations } from 'next-intl';
import { ArrowUpDown, ChevronDown, FileUp, Layers, MessageSquarePlus, MoreHorizontal, Swords, X } from 'lucide-react';

/**
 * Where ✕ leads: back, when the previous page is ours; the dashboard when the
 * coach was opened first (a new tab) or from another site.
 */
export function exitTarget({
  historyLength,
  referrer,
  origin,
}: {
  historyLength: number;
  referrer: string;
  origin: string;
}): 'back' | 'dashboard' {
  if (historyLength <= 1) return 'dashboard';
  if (!referrer) return 'back';
  try {
    return new URL(referrer).origin === origin ? 'back' : 'dashboard';
  } catch {
    return 'dashboard';
  }
}

export interface ContextMenuActions {
  /** Null while a game is on (one game at a time). */
  onPlay: (() => void) | null;
  onImport: () => void;
  onFlip: () => void;
  /** Null without opened games. */
  onBoardTabs: (() => void) | null;
  onNewSession: () => void;
}

interface ContextBarProps {
  title: string;
  subtitle?: string;
  sessionsOpen: boolean;
  onOpenSessions: () => void;
  /** Beside ⋯: the opened-boards chip, when there are any. */
  trailing?: React.ReactNode;
  menu: ContextMenuActions;
}

const iconButton =
  'flex h-11 w-11 shrink-0 items-center justify-center rounded-xl text-(--coach-text) transition-colors hover:bg-white/5 focus-visible:outline focus-visible:outline-2 focus-visible:outline-(--coach-accent) active:bg-white/10';

/** The coach's 48px bar on phones: ✕ · session title ▾ (sessions) · ⋯ menu. */
export default function ContextBar({ title, subtitle, sessionsOpen, onOpenSessions, trailing, menu }: ContextBarProps) {
  const t = useTranslations('coach');
  const router = useRouter();
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!menuOpen) return;
    menuRef.current?.querySelector<HTMLElement>('[role="menuitem"]')?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setMenuOpen(false);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [menuOpen]);

  const exit = () => {
    const target = exitTarget({
      historyLength: window.history.length,
      referrer: document.referrer,
      origin: window.location.origin,
    });
    if (target === 'back') router.back();
    else router.push('/dashboard');
  };

  const items: Array<{ key: string; icon: typeof Swords; label: string; run: (() => void) | null }> = [
    { key: 'play', icon: Swords, label: t('playWithCoach'), run: menu.onPlay },
    { key: 'import', icon: FileUp, label: t('importGame'), run: menu.onImport },
    { key: 'flip', icon: ArrowUpDown, label: t('flipBoard'), run: menu.onFlip },
    ...(menu.onBoardTabs ? [{ key: 'tabs', icon: Layers, label: t('viewerTabs'), run: menu.onBoardTabs }] : []),
    { key: 'new', icon: MessageSquarePlus, label: t('newSession'), run: menu.onNewSession },
  ];

  return (
    <header
      className="relative z-20 flex shrink-0 items-center gap-1 bg-(--coach-bg) px-1.5 pt-[env(safe-area-inset-top)]"
      style={{ height: 'var(--coach-bar-h)' }}
      data-testid="coach-context-bar"
    >
      <button type="button" onClick={exit} aria-label={t('exitCoach')} title={t('exitCoach')} className={iconButton}>
        <X size={22} aria-hidden />
      </button>

      <button
        type="button"
        onClick={onOpenSessions}
        aria-haspopup="dialog"
        aria-expanded={sessionsOpen}
        aria-label={t('openSessions', { title })}
        className="flex min-h-11 min-w-0 flex-1 flex-col items-center justify-center rounded-xl px-1 transition-colors hover:bg-white/5 focus-visible:outline focus-visible:outline-2 focus-visible:outline-(--coach-accent)"
      >
        <span className="flex max-w-full items-center gap-1">
          <span className="truncate text-base font-semibold leading-tight text-(--coach-text)">{title}</span>
          <ChevronDown size={16} aria-hidden className="shrink-0 text-(--coach-muted)" />
        </span>
        {subtitle && <span className="max-w-full truncate text-xs font-medium leading-tight text-(--coach-muted)">{subtitle}</span>}
      </button>

      {trailing}

      <div className="relative">
        <button
          type="button"
          onClick={() => setMenuOpen((open) => !open)}
          aria-label={t('moreActions')}
          title={t('moreActions')}
          aria-haspopup="menu"
          aria-expanded={menuOpen}
          className={iconButton}
          data-testid="coach-more"
        >
          <MoreHorizontal size={22} aria-hidden />
        </button>
        {menuOpen && (
          <>
            <div className="fixed inset-0 z-10" onClick={() => setMenuOpen(false)} aria-hidden />
            <div
              ref={menuRef}
              role="menu"
              aria-label={t('moreActions')}
              className="animate-fade-in absolute top-full right-0 z-20 mt-1 w-64 overflow-hidden rounded-2xl border border-(--coach-border) bg-(--coach-surface) p-1 shadow-2xl"
            >
              {items.map(({ key, icon: Icon, label, run }) => (
                <button
                  key={key}
                  type="button"
                  role="menuitem"
                  disabled={!run}
                  onClick={() => {
                    setMenuOpen(false);
                    run?.();
                  }}
                  className="flex min-h-12 w-full items-center gap-3 rounded-xl px-3 text-left text-[15px] text-(--coach-text) transition-colors hover:bg-(--coach-surface-2) focus-visible:outline focus-visible:outline-2 focus-visible:outline-(--coach-accent) disabled:opacity-40"
                >
                  <Icon size={20} aria-hidden className="shrink-0 text-(--coach-muted)" />
                  {label}
                </button>
              ))}
            </div>
          </>
        )}
      </div>
    </header>
  );
}
