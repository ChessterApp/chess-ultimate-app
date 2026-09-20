'use client';

import React, { useCallback, useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import { coachApi, type SessionSummary } from '@/lib/coach/boards-api';

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

  const refresh = useCallback(async () => {
    const list = await coachApi.listSessions();
    setSessions(list ?? []);
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const rename = async (s: SessionSummary) => {
    const title = window.prompt(t('renamePrompt'), s.title || '');
    if (title === null) return;
    const updated = await coachApi.updateSession(s.id, { title });
    if (updated) setSessions((prev) => (prev ?? []).map((x) => (x.id === s.id ? updated : x)));
  };

  const remove = async (s: SessionSummary) => {
    if (!window.confirm(`${t('deleteSession')}?`)) return;
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
              className={`group flex items-start gap-2 px-3 py-2 border-b border-white/5 cursor-pointer ${
                s.id === currentSessionId ? 'bg-white/10' : 'hover:bg-white/5'
              }`}
              onClick={() => {
                onSelect(s.id);
                onClose();
              }}
            >
              <div className="min-w-0 flex-1">
                <div className="text-sm text-white truncate">
                  {s.title || s.preview || t('untitledSession')}
                </div>
                <div className="text-[11px] text-gray-500 flex gap-2">
                  <span>{formatWhen(s.updated_at)}</span>
                  <span>{t('messagesCount', { count: s.message_count })}</span>
                </div>
              </div>
              <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100">
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    void rename(s);
                  }}
                  className="text-gray-400 hover:text-white text-xs"
                  title={t('renameSession')}
                >
                  ✎
                </button>
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    void remove(s);
                  }}
                  className="text-gray-400 hover:text-red-400 text-xs"
                  title={t('deleteSession')}
                >
                  🗑
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
