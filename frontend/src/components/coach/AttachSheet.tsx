'use client';

import React, { useEffect, useRef } from 'react';
import { useTranslations } from 'next-intl';
import { Camera, ClipboardPaste, FileUp, Link2, ScrollText } from 'lucide-react';

export type AttachKind = 'paste' | 'upload' | 'photo-position' | 'photo-scoresheet' | 'link';

interface AttachSheetProps {
  open: boolean;
  onClose: () => void;
  onPick: (kind: AttachKind) => void;
}

const ITEMS: Array<{ kind: AttachKind; icon: React.ComponentType<{ size?: number; 'aria-hidden'?: boolean; className?: string }>; label: string }> = [
  { kind: 'paste', icon: ClipboardPaste, label: 'attachPaste' },
  { kind: 'upload', icon: FileUp, label: 'attachUpload' },
  { kind: 'photo-position', icon: Camera, label: 'photoToPosition' },
  { kind: 'photo-scoresheet', icon: ScrollText, label: 'scoresheetToGame' },
  { kind: 'link', icon: Link2, label: 'attachLink' },
];

/**
 * What the composer's `+` offers: paste / upload a game, a photo of a board or
 * a scoresheet, a game link. A bottom sheet on phones, a menu above the `+` on
 * a desktop (the host is its positioning box).
 */
export default function AttachSheet({ open, onClose, onPick }: AttachSheetProps) {
  const t = useTranslations('coach');
  const listRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    listRef.current?.querySelector<HTMLElement>('[role="menuitem"]')?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-[60] flex items-end lg:absolute lg:inset-auto lg:bottom-full lg:left-0 lg:z-20 lg:mb-2 lg:block">
      <div className="animate-fade-in absolute inset-0 bg-black/60 lg:hidden" onClick={onClose} aria-hidden />
      <div
        ref={listRef}
        role="menu"
        aria-label={t('attachMenu')}
        data-testid="attach-sheet"
        className="animate-fade-in relative w-full rounded-t-[22px] border-t border-(--coach-border) bg-(--coach-surface) px-2 pt-2 pb-[calc(0.75rem+env(safe-area-inset-bottom))] shadow-(--coach-shadow) lg:w-72 lg:rounded-2xl lg:border lg:pb-2"
      >
        <div className="mx-auto mb-2 h-[5px] w-[38px] rounded-full bg-(--coach-grabber) lg:hidden" aria-hidden />
        {ITEMS.map(({ kind, icon: Icon, label }) => (
          <button
            key={kind}
            type="button"
            role="menuitem"
            onClick={() => {
              onClose();
              onPick(kind);
            }}
            className="flex min-h-12 w-full items-center gap-3 rounded-xl px-3 text-left text-[15px] text-(--coach-text) transition-colors hover:bg-(--coach-surface-2) focus-visible:outline focus-visible:outline-2 focus-visible:outline-(--coach-accent) active:bg-(--coach-surface-2)"
          >
            <Icon size={20} aria-hidden className="shrink-0 text-(--coach-muted)" />
            {t(label)}
          </button>
        ))}
      </div>
    </div>
  );
}
