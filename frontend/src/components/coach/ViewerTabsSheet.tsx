'use client';

import React, { useEffect, useRef, useState } from 'react';
import { useTranslations } from 'next-intl';
import { Layers, Sparkles, X } from 'lucide-react';

export interface ViewerTab {
  id: string;
  title: string;
  subtitle?: string;
}

interface ViewerTabsSheetProps {
  tabs: ViewerTab[];
  /** The tab shown; null = the coach's (study) board. */
  activeId: string | null;
  onSelect: (id: string | null) => void;
  onClose: (id: string) => void;
}

const focusRing = 'focus-visible:outline focus-visible:outline-2 focus-visible:outline-(--coach-accent)';

/**
 * Opened games as a stack chip (`▣ 3`) that opens a sheet: the coach's board
 * plus every opened game — tap to switch, × to close.
 */
export default function ViewerTabsSheet({ tabs, activeId, onSelect, onClose }: ViewerTabsSheetProps) {
  const t = useTranslations('coach');
  const [open, setOpen] = useState(false);
  const sheetRef = useRef<HTMLDivElement>(null);
  const active = tabs.find((g) => g.id === activeId);

  useEffect(() => {
    if (!open) return;
    sheetRef.current?.querySelector<HTMLElement>('[aria-current="true"]')?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open]);

  const pick = (id: string | null) => {
    onSelect(id);
    setOpen(false);
  };

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        aria-haspopup="dialog"
        aria-expanded={open}
        aria-label={t('viewerTabsCount', { count: tabs.length + 1 })}
        data-testid="viewer-tabs-chip"
        className={`flex min-h-11 max-w-full items-center gap-2 rounded-full border border-(--coach-border) bg-(--coach-surface) px-3 text-sm text-(--coach-text) transition-colors hover:bg-(--coach-surface-2) ${focusRing}`}
      >
        <Layers size={16} aria-hidden className="shrink-0 text-(--coach-accent)" />
        <span className="tabular-nums">{tabs.length + 1}</span>
        <span className="truncate text-(--coach-muted)">{active ? active.title : t('coachBoard')}</span>
      </button>

      {open && (
        <div className="fixed inset-0 z-[60] flex items-end justify-center lg:items-center">
          <div className="animate-fade-in absolute inset-0 bg-black/60" onClick={() => setOpen(false)} aria-hidden />
          <div
            ref={sheetRef}
            role="dialog"
            aria-modal="true"
            aria-labelledby="viewer-tabs-title"
            data-testid="viewer-tabs-sheet"
            className="animate-fade-in relative max-h-[70dvh] w-full max-w-md overflow-y-auto rounded-t-2xl border border-(--coach-border) bg-(--coach-surface) px-2 pt-2 pb-[calc(0.75rem+env(safe-area-inset-bottom))] shadow-2xl lg:rounded-2xl lg:pb-2"
          >
            <div className="mx-auto mb-1 h-1 w-10 rounded-full bg-white/20 lg:hidden" aria-hidden />
            <h2 id="viewer-tabs-title" className="px-2 py-2 text-base font-semibold text-(--coach-text)">
              {t('viewerTabs')}
            </h2>
            <ul className="flex flex-col gap-1">
              <li>
                <button
                  type="button"
                  onClick={() => pick(null)}
                  aria-current={activeId === null}
                  className={`flex min-h-12 w-full items-center gap-3 rounded-xl px-3 text-left text-sm transition-colors ${focusRing} ${
                    activeId === null ? 'bg-(--coach-accent-soft) text-(--coach-text)' : 'text-(--coach-text) hover:bg-white/5'
                  }`}
                >
                  <Sparkles size={16} aria-hidden className="shrink-0 text-(--coach-accent)" />
                  {t('coachBoard')}
                </button>
              </li>
              {tabs.map((tab) => (
                <li key={tab.id} className="flex items-center gap-1">
                  <button
                    type="button"
                    onClick={() => pick(tab.id)}
                    aria-current={activeId === tab.id}
                    className={`flex min-h-12 min-w-0 flex-1 flex-col justify-center rounded-xl px-3 text-left transition-colors ${focusRing} ${
                      activeId === tab.id ? 'bg-(--coach-accent-soft)' : 'hover:bg-white/5'
                    }`}
                  >
                    <span className="truncate text-sm text-(--coach-text)">{tab.title}</span>
                    {tab.subtitle && <span className="truncate text-xs text-(--coach-muted)">{tab.subtitle}</span>}
                  </button>
                  <button
                    type="button"
                    onClick={() => onClose(tab.id)}
                    aria-label={`${t('closeTab')}: ${tab.title}`}
                    className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-full text-(--coach-muted) transition-colors hover:bg-white/5 hover:text-(--coach-text) ${focusRing}`}
                  >
                    <X size={18} aria-hidden />
                  </button>
                </li>
              ))}
            </ul>
          </div>
        </div>
      )}
    </>
  );
}
