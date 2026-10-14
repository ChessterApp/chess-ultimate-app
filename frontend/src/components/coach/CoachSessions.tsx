'use client';

import React, { useCallback, useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import { MoreHorizontal, Plus, X } from 'lucide-react';
import { coachApi, type SessionSummary } from '@/lib/coach/boards-api';
import CoachDialog from './CoachDialog';

interface CoachSessionsProps {
  currentSessionId: string | null;
  onSelect: (id: string) => void;
  onNew: () => void;
  onClose: () => void;
  /** 'dropdown' under the desktop header; 'sheet' from the mobile title ▾. */
  variant?: 'dropdown' | 'sheet';
}

const focusRing = 'focus-visible:outline focus-visible:outline-2 focus-visible:outline-(--coach-accent)';

function formatWhen(seconds: number): string {
  const d = new Date(seconds * 1000);
  const today = new Date();
  const sameDay = d.toDateString() === today.toDateString();
  return sameDay
    ? d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' })
    : d.toLocaleDateString(undefined, { day: '2-digit', month: 'short' });
}

/**
 * Drop-down list of the student's coaching sessions: switch, rename, delete,
 * start a new one. Sessions are persisted by Hermes (coach_sessions); before
 * this the page only remembered the last session id in localStorage.
 */
export default function CoachSessions({ currentSessionId, onSelect, onNew, onClose, variant = 'dropdown' }: CoachSessionsProps) {
  const t = useTranslations('coach');
  const [sessions, setSessions] = useState<SessionSummary[] | null>(null);
  // Row whose ⋯ menu is open, and the session a rename/delete dialog is about.
  const [menuFor, setMenuFor] = useState<string | null>(null);
  const [dialog, setDialog] = useState<{ kind: 'rename' | 'delete'; session: SessionSummary } | null>(null);

  const refresh = useCallback(async () => {
    const list = await coachApi.listSessions();
    setSessions(list ?? []);
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const label = (s: SessionSummary) => s.title || s.preview || t('untitledSession');

  const rename = async (s: SessionSummary, title: string) => {
    const updated = await coachApi.updateSession(s.id, { title });
    if (updated) setSessions((prev) => (prev ?? []).map((x) => (x.id === s.id ? updated : x)));
  };

  const remove = async (s: SessionSummary) => {
    const ok = await coachApi.deleteSession(s.id);
    if (ok) {
      setSessions((prev) => (prev ?? []).filter((x) => x.id !== s.id));
      if (s.id === currentSessionId) onNew();
    }
  };

  const sheet = variant === 'sheet';
  const newSession = () => {
    onNew();
    onClose();
  };

  const panel = (
    <div
      className={
        sheet
          ? 'animate-fade-in relative flex max-h-[80dvh] w-full flex-col rounded-t-[22px] border-t border-(--coach-border) bg-(--coach-surface) pb-[env(safe-area-inset-bottom)] shadow-(--coach-shadow)'
          : 'absolute right-0 top-full z-30 mt-1 max-h-[70vh] w-80 overflow-y-auto rounded-xl border border-(--coach-border) bg-(--coach-surface) shadow-xl'
      }
      role="dialog"
      aria-modal={sheet || undefined}
      aria-label={t('sessionsTitle')}
      data-testid="coach-sessions"
    >
      {sheet && <div className="mx-auto mt-2 mb-1 h-[5px] w-[38px] shrink-0 rounded-full bg-(--coach-grabber)" aria-hidden />}
      <div className="flex shrink-0 items-center justify-between border-b border-(--coach-border) py-1 pl-4 pr-1">
        <span className="text-base font-semibold text-(--coach-text)">{t('sessionsTitle')}</span>
        <div className="flex items-center gap-1">
          {!sheet && (
            <button
              type="button"
              onClick={newSession}
              className={`min-h-11 rounded-lg px-2 text-sm text-(--coach-accent-text) hover:bg-white/5 ${focusRing}`}
            >
              + {t('newSession')}
            </button>
          )}
          <button
            type="button"
            onClick={onClose}
            className={`flex h-11 w-11 items-center justify-center rounded-lg text-(--coach-muted) hover:bg-white/5 hover:text-(--coach-text) ${focusRing}`}
            aria-label={t('gameClose')}
          >
            <X size={20} aria-hidden />
          </button>
        </div>
      </div>

      <div className={sheet ? 'min-h-0 flex-1 overflow-y-auto px-2 py-2' : ''}>
        {sheet && (
          <button
            type="button"
            onClick={newSession}
            className={`mb-1 flex min-h-12 w-full items-center gap-3 rounded-xl px-3 text-left text-[15px] font-medium text-(--coach-accent-text) hover:bg-white/5 ${focusRing}`}
          >
            <Plus size={20} aria-hidden />
            {t('newSession')}
          </button>
        )}
        {sessions === null ? (
          <div className="px-3 py-4 text-xs text-(--coach-muted)">…</div>
        ) : sessions.length === 0 ? (
          <div className="px-3 py-4 text-xs text-(--coach-muted)">{t('noSessions')}</div>
        ) : (
          <ul>
            {sessions.map((s) => (
              <li
                key={s.id}
                className={`relative flex cursor-pointer items-center gap-2 py-1 pl-3 pr-1 ${
                  sheet ? 'rounded-xl' : 'border-b border-(--coach-border)'
                } ${s.id === currentSessionId ? 'bg-(--coach-accent-soft)' : 'hover:bg-white/5'}`}
                onClick={() => {
                  onSelect(s.id);
                  onClose();
                }}
              >
                <div className="min-w-0 flex-1">
                  <div className="truncate text-sm text-(--coach-text)">{label(s)}</div>
                  <div className="flex gap-2 text-[11px] text-(--coach-muted)">
                    <span>{formatWhen(s.updated_at)}</span>
                    <span>{t('messagesCount', { count: s.message_count })}</span>
                  </div>
                </div>
                <button
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation();
                    setMenuFor((open) => (open === s.id ? null : s.id));
                  }}
                  aria-label={t('sessionActions')}
                  aria-haspopup="menu"
                  aria-expanded={menuFor === s.id}
                  className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-lg text-(--coach-muted) hover:bg-white/10 hover:text-(--coach-text) ${focusRing}`}
                >
                  <MoreHorizontal size={18} aria-hidden />
                </button>
                {menuFor === s.id && (
                  <div
                    role="menu"
                    className="absolute right-2 top-full z-10 -mt-1 w-44 overflow-hidden rounded-xl border border-(--coach-border) bg-(--coach-surface-2) shadow-lg"
                    onClick={(e) => e.stopPropagation()}
                  >
                    <button
                      type="button"
                      role="menuitem"
                      onClick={() => {
                        setMenuFor(null);
                        setDialog({ kind: 'rename', session: s });
                      }}
                      className="block min-h-11 w-full px-3 text-left text-sm text-(--coach-text) hover:bg-white/10"
                    >
                      {t('renameSession')}
                    </button>
                    <button
                      type="button"
                      role="menuitem"
                      onClick={() => {
                        setMenuFor(null);
                        setDialog({ kind: 'delete', session: s });
                      }}
                      className="block min-h-11 w-full border-t border-(--coach-border) px-3 text-left text-sm text-(--coach-danger) hover:bg-white/10"
                    >
                      {t('deleteSession')}
                    </button>
                  </div>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );

  return (
    <>
      {sheet ? (
        <div className="fixed inset-0 z-[60] flex items-end">
          <div className="animate-fade-in absolute inset-0 bg-black/60" onClick={onClose} aria-hidden />
          {panel}
        </div>
      ) : (
        panel
      )}

      <CoachDialog
        open={dialog?.kind === 'rename'}
        title={t('renameSession')}
        inputLabel={t('renamePrompt')}
        initialValue={dialog?.kind === 'rename' ? dialog.session.title || '' : ''}
        confirmLabel={t('save')}
        onCancel={() => setDialog(null)}
        onConfirm={(title) => {
          if (dialog) void rename(dialog.session, title);
          setDialog(null);
        }}
      />
      <CoachDialog
        open={dialog?.kind === 'delete'}
        title={t('deleteSession')}
        message={dialog ? t('deleteSessionConfirm', { title: label(dialog.session) }) : undefined}
        confirmLabel={t('delete')}
        danger
        onCancel={() => setDialog(null)}
        onConfirm={() => {
          if (dialog) void remove(dialog.session);
          setDialog(null);
        }}
      />
    </>
  );
}
