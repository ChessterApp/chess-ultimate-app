'use client';

import React, { useState, useEffect } from 'react';
import { useTranslations } from 'next-intl';
import { ChatSession } from '@/hooks/useChatSessions';
import ConfirmDialog from './ui/ConfirmDialog';

interface ChatSidebarProps {
  sessions: ChatSession[];
  currentSessionId: string | null;
  onNewChat: () => void;
  onSelectSession: (sessionId: string) => void;
  onDeleteSession: (sessionId: string) => void;
  onRenameSession: (sessionId: string, newTitle: string) => void;
  onToggleCollapse: () => void;
  isCollapsed?: boolean;
  currentBoardFen?: string;
}

const ChatSidebar: React.FC<ChatSidebarProps> = ({
  sessions,
  currentSessionId,
  onNewChat,
  onSelectSession,
  onDeleteSession,
  onRenameSession,
  onToggleCollapse,
  isCollapsed = false,
}) => {
  const t = useTranslations();
  const [editingSessionId, setEditingSessionId] = useState<string | null>(null);
  const [editingTitle, setEditingTitle] = useState('');
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [sessionToDelete, setSessionToDelete] = useState<string | null>(null);
  const [mobileOpen, setMobileOpen] = useState(false);

  // Lock body scroll while the mobile drawer is open
  useEffect(() => {
    if (!mobileOpen || typeof document === 'undefined') return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.body.style.overflow = prev;
    };
  }, [mobileOpen]);

  const handleStartEdit = (session: ChatSession) => {
    setEditingSessionId(session.id);
    setEditingTitle(session.title);
  };

  const handleSaveEdit = () => {
    if (editingSessionId && editingTitle.trim()) {
      onRenameSession(editingSessionId, editingTitle.trim());
    }
    setEditingSessionId(null);
    setEditingTitle('');
  };

  const handleCancelEdit = () => {
    setEditingSessionId(null);
    setEditingTitle('');
  };

  // On mobile, selecting or creating a chat should close the drawer
  const handleSelectSession = (sessionId: string) => {
    onSelectSession(sessionId);
    setMobileOpen(false);
  };

  const handleNewChat = () => {
    onNewChat();
    setMobileOpen(false);
  };

  // Shared session list — reused by the desktop sidebar and the mobile drawer
  const sessionList = (
    <div className="flex-1 overflow-y-auto custom-scrollbar">
      {sessions.length === 0 ? (
        <div className="p-6 text-center">
          <div className="text-gray-400 dark:text-purple-300/60 text-sm">
            {t('analysis.noChatsYet')}
          </div>
          <div className="text-gray-500 dark:text-slate-400 text-xs mt-2">
            {t('analysis.startNewChat')}
          </div>
        </div>
      ) : (
        <div className="p-3 space-y-2">
          {sessions
            .sort((a, b) => b.updatedAt - a.updatedAt)
            .map((session) => (
              <div
                key={session.id}
                className={`group relative rounded-lg transition-all duration-200 ${
                  session.id === currentSessionId
                    ? 'bg-purple-50 dark:bg-purple-600/20 border-2 border-purple-300 dark:border-purple-500/50 shadow-sm dark:shadow-lg dark:shadow-purple-900/30'
                    : 'bg-gray-50 dark:bg-slate-800/20 border-2 border-transparent hover:bg-gray-100 dark:hover:bg-slate-700/30 hover:border-purple-200 dark:hover:border-purple-500/30'
                }`}
              >
                {editingSessionId === session.id ? (
                  <div className="p-3">
                    <input
                      type="text"
                      value={editingTitle}
                      onChange={(e) => setEditingTitle(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter') handleSaveEdit();
                        if (e.key === 'Escape') handleCancelEdit();
                      }}
                      onBlur={handleSaveEdit}
                      className="w-full bg-white dark:bg-slate-900/80 border border-gray-300 dark:border-purple-500/50 text-gray-900 dark:text-white text-sm px-3 py-2 rounded-lg focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent"
                      autoFocus
                    />
                  </div>
                ) : (
                  <div
                    onClick={() => handleSelectSession(session.id)}
                    className="w-full p-3 text-left flex justify-between items-start cursor-pointer"
                  >
                    <div className="flex-1 min-w-0">
                      <div className={`text-sm font-medium truncate flex items-center ${
                        session.id === currentSessionId ? 'text-purple-700 dark:text-purple-200' : 'text-gray-800 dark:text-slate-200'
                      }`}>
                        {session.title}
                      </div>
                      <div className="flex items-center space-x-2 mt-1">
                        <div className="text-xs text-gray-500 dark:text-slate-400">
                          {new Date(session.updatedAt).toLocaleDateString()}
                        </div>
                        {session.messages.length > 0 && (
                          <div className="text-xs text-purple-500 dark:text-purple-400/60">
                            • {session.messages.length} msg{session.messages.length !== 1 ? 's' : ''}
                          </div>
                        )}
                      </div>
                    </div>

                    {/* Action buttons (always tappable on mobile, hover on desktop) */}
                    <div className="opacity-100 md:opacity-0 md:group-hover:opacity-100 flex items-center space-x-1 ml-2 transition-opacity">
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          handleStartEdit(session);
                        }}
                        className="p-1.5 text-gray-400 dark:text-slate-400 hover:text-purple-600 dark:hover:text-purple-300 hover:bg-purple-100 dark:hover:bg-purple-500/20 rounded transition-colors"
                        title={t('analysis.renameChat')}
                      >
                        <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" />
                        </svg>
                      </button>
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          setSessionToDelete(session.id);
                          setDeleteDialogOpen(true);
                        }}
                        className="p-1.5 text-gray-400 dark:text-slate-400 hover:text-red-500 dark:hover:text-red-400 hover:bg-red-100 dark:hover:bg-red-500/20 rounded transition-colors"
                        title={t('analysis.deleteChat')}
                      >
                        <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                        </svg>
                      </button>
                    </div>
                  </div>
                )}
              </div>
            ))}
        </div>
      )}
    </div>
  );

  // Shared footer with session counter
  const footer = (
    <div className="p-4 border-t border-gray-200 dark:border-purple-500/20">
      <div className="flex items-center justify-center">
        <div className="text-gray-500 dark:text-slate-400 text-xs flex items-center space-x-2">
          <svg className="w-4 h-4 text-purple-500 dark:text-purple-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" />
          </svg>
          <span>
            {t('analysis.chatCount', { count: sessions.length })}
          </span>
        </div>
      </div>
    </div>
  );

  return (
    <>
      {/* Desktop: collapsed rail */}
      {isCollapsed && (
        <div className="w-16 bg-white dark:bg-gradient-to-b dark:from-purple-950/40 dark:to-slate-900/40 backdrop-blur-xl border-r border-gray-200 dark:border-purple-500/20 flex-col shadow-sm dark:shadow-2xl dark:shadow-purple-900/50 hidden md:flex">
          <div className="p-3">
            <button
              onClick={onToggleCollapse}
              className="w-full aspect-square flex items-center justify-center rounded-lg bg-purple-600 hover:bg-purple-500 text-white transition-all duration-300 shadow-lg hover:scale-105"
              title="Expand Session Panel"
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
              </svg>
            </button>
          </div>
        </div>
      )}

      {/* Desktop: expanded sidebar */}
      {!isCollapsed && (
        <div className="w-80 bg-white dark:bg-gradient-to-b dark:from-purple-950/40 dark:to-slate-900/40 backdrop-blur-xl border-r border-gray-200 dark:border-purple-500/20 flex-col h-full shadow-sm dark:shadow-2xl dark:shadow-purple-900/50 hidden md:flex">
          {/* Header with New Chat and Collapse buttons */}
          <div className="p-4 border-b border-gray-200 dark:border-purple-500/20 space-y-2">
            <button
              onClick={onNewChat}
              className="w-full flex items-center justify-center space-x-2 px-4 py-3 rounded-lg bg-purple-600 hover:bg-purple-500 text-white font-medium transition-all duration-300 shadow-lg hover:scale-[1.02]"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
              </svg>
              <span>{t('analysis.newChat')}</span>
            </button>
            <button
              onClick={onToggleCollapse}
              className="w-full flex items-center justify-center space-x-2 px-4 py-2 rounded-lg bg-gray-100 dark:bg-slate-800/30 hover:bg-gray-200 dark:hover:bg-slate-700/40 text-gray-600 dark:text-slate-300 text-sm font-medium transition-all duration-300 border border-gray-200 dark:border-purple-500/20 hover:border-gray-300 dark:hover:border-purple-500/40"
              title="Collapse Panel"
            >
              <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 19l-7-7 7-7m8 14l-7-7 7-7" />
              </svg>
              <span>{t('analysis.collapse')}</span>
            </button>
          </div>

          {sessionList}
          {footer}
        </div>
      )}

      {/* Mobile: floating trigger (44px+ touch target) */}
      <button
        type="button"
        onClick={() => setMobileOpen(true)}
        aria-label="Open chat sessions"
        aria-expanded={mobileOpen}
        className="md:hidden fixed bottom-20 left-4 z-40 h-12 w-12 flex items-center justify-center rounded-full bg-purple-600 hover:bg-purple-500 text-white shadow-lg"
      >
        <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" />
        </svg>
      </button>

      {/* Mobile: backdrop */}
      {mobileOpen && (
        <div
          className="md:hidden fixed inset-0 z-40 bg-black/50"
          onClick={() => setMobileOpen(false)}
          aria-hidden="true"
        />
      )}

      {/* Mobile: slide-in drawer */}
      <aside
        aria-label="Chat sessions"
        aria-hidden={!mobileOpen}
        className={`md:hidden fixed inset-y-0 left-0 z-50 w-80 max-w-[85vw] flex flex-col bg-white dark:bg-gradient-to-b dark:from-purple-950/40 dark:to-slate-900/40 backdrop-blur-xl border-r border-gray-200 dark:border-purple-500/20 shadow-xl transform transition-transform duration-200 ease-in-out ${
          mobileOpen ? 'translate-x-0' : '-translate-x-full'
        }`}
      >
        <div className="p-4 border-b border-gray-200 dark:border-purple-500/20 flex items-center gap-2">
          <button
            onClick={handleNewChat}
            className="flex-1 flex items-center justify-center space-x-2 px-4 py-3 rounded-lg bg-purple-600 hover:bg-purple-500 text-white font-medium transition-all duration-300 shadow-lg"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
            </svg>
            <span>{t('analysis.newChat')}</span>
          </button>
          <button
            type="button"
            onClick={() => setMobileOpen(false)}
            aria-label="Close chat sessions"
            className="h-11 w-11 flex items-center justify-center rounded-lg bg-gray-100 dark:bg-slate-800/30 hover:bg-gray-200 dark:hover:bg-slate-700/40 text-gray-600 dark:text-slate-300 border border-gray-200 dark:border-purple-500/20"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {sessionList}
        {footer}
      </aside>

      {/* Custom Scrollbar Styles */}
      <style jsx>{`
        .custom-scrollbar::-webkit-scrollbar {
          width: 6px;
        }
        .custom-scrollbar::-webkit-scrollbar-track {
          background: rgba(100, 116, 139, 0.1);
          border-radius: 3px;
        }
        .custom-scrollbar::-webkit-scrollbar-thumb {
          background: rgba(147, 51, 234, 0.3);
          border-radius: 3px;
        }
        .custom-scrollbar::-webkit-scrollbar-thumb:hover {
          background: rgba(147, 51, 234, 0.5);
        }
      `}</style>

      {/* Delete Confirmation Dialog */}
      <ConfirmDialog
        open={deleteDialogOpen}
        title={t('analysis.deleteChat')}
        message={t('analysis.deleteConfirmMessage')}
        confirmText={t('common.delete')}
        cancelText={t('common.cancel')}
        variant="danger"
        onConfirm={() => {
          if (sessionToDelete) {
            onDeleteSession(sessionToDelete);
          }
          setDeleteDialogOpen(false);
          setSessionToDelete(null);
        }}
        onCancel={() => {
          setDeleteDialogOpen(false);
          setSessionToDelete(null);
        }}
      />
    </>
  );
};

export default ChatSidebar;
