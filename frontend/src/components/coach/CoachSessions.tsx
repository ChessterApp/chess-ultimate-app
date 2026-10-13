'use client';

import React, { useCallback, useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import { coachApi, type SessionSummary } from '@/lib/coach/boards-api';
import CoachDialog from './CoachDialog';

interface CoachSessionsProps {
  currentSessionId: string | null;
  onSelect: (id: string) => void;
  onNew: () => void;
  onClose: () => void;
}

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
export default function CoachSessions({ currentSessionId, onSelect, onNew, onClose }: CoachSessionsProps) {
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

  return (
    <div
      className="absolute right-0 top-full mt-1 w-80 max-h-[70vh] overflow-y-auto rounded-lg border border-white/10 bg-[#1b1b1f] shadow-xl z-30"
      role="dialog"
      aria-label={t('sessionsTitle')}
    >
      <div className="flex items-center justify-between px-3 py-2 border-b border-white/10">
        <span className="text-sm font-medium text-white">{t('sessionsTitle')}</span>
        <div className="flex items-center gap-2">
          <button
            onClick={() => {
              onNew();
              onClose();
            }}
            className="text-xs text-emerald-400 hover:text-emerald-300"
          >
            + {t('newSession')}
          </button>
          <button onClick={onClose} className="text-gray-400 hover:text-white text-sm" aria-label="close">
            ×
          </button>
        </div>
      </div>

      {sessions === null ? (
        <div className="px-3 py-4 text-xs text-gray-400">…</div>
      ) : sessions.length === 0 ? (
        <div className="px-3 py-4 text-xs text-gray-400">{t('noSessions')}</div>
      ) : (
        <ul>
          {sessions.map((s) => (
            <li
              key={s.id}
              className={`relative flex items-center gap-2 pl-3 pr-1 py-1 border-b border-white/5 cursor-pointer ${
                s.id === currentSessionId ? 'bg-white/10' : 'hover:bg-white/5'
              }`}
              onClick={() => {
                onSelect(s.id);
                onClose();
              }}
            >
              <div className="min-w-0 flex-1">
                <div className="text-sm text-white truncate">{label(s)}</div>
                <div className="text-[11px] text-gray-500 flex gap-2">
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
                className="flex h-11 w-11 shrink-0 items-center justify-center rounded-lg text-gray-400 hover:bg-white/10 hover:text-white focus-visible:outline focus-visible:outline-2 focus-visible:outline-blue-400"
              >
                ⋯
              </button>
              {menuFor === s.id && (
                <div
                  role="menu"
                  className="absolute right-2 top-full z-10 -mt-1 w-44 overflow-hidden rounded-lg border border-white/10 bg-[#24242a] shadow-lg"
                  onClick={(e) => e.stopPropagation()}
                >
                  <button
                    type="button"
                    role="menuitem"
                    onClick={() => {
                      setMenuFor(null);
                      setDialog({ kind: 'rename', session: s });
                    }}
                    className="block min-h-11 w-full px-3 text-left text-sm text-gray-200 hover:bg-white/10"
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
                    className="block min-h-11 w-full border-t border-white/5 px-3 text-left text-sm text-red-300 hover:bg-white/10"
                  >
                    {t('deleteSession')}
                  </button>
                </div>
              )}
            </li>
          ))}
        </ul>
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
    </div>
  );
}
