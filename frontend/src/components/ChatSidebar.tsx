'use client';

import React, { useState } from 'react';
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

  if (isCollapsed) {
    return (
      <div className="w-16 bg-gradient-to-b from-purple-950/40 to-slate-900/40 backdrop-blur-xl border-r border-purple-500/20 flex flex-col shadow-2xl shadow-purple-900/50 hidden md:flex">
        <div className="p-3">
          <button
            onClick={onToggleCollapse}
            className="w-full aspect-square flex items-center justify-center rounded-lg bg-gradient-to-br from-purple-600 to-purple-800 hover:from-purple-500 hover:to-purple-700 text-white transition-all duration-300 shadow-lg shadow-purple-900/50 hover:shadow-purple-600/50 hover:scale-105"
            title="Expand Session Panel"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
            </svg>
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="w-80 md:w-80 bg-gradient-to-b from-purple-950/40 to-slate-900/40 backdrop-blur-xl border-r border-purple-500/20 flex flex-col h-full shadow-2xl shadow-purple-900/50 hidden md:flex">
      {/* Header with New Chat and Collapse buttons */}
      <div className="p-4 border-b border-purple-500/20 space-y-2">
        <button
          onClick={onNewChat}
          className="w-full flex items-center justify-center space-x-2 px-4 py-3 rounded-lg bg-gradient-to-r from-purple-600 to-purple-800 hover:from-purple-500 hover:to-purple-700 text-white font-medium transition-all duration-300 shadow-lg shadow-purple-900/50 hover:shadow-purple-600/50 hover:scale-[1.02]"
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
          </svg>
          <span>{t('analysis.newChat')}</span>
        </button>
        <button
          onClick={onToggleCollapse}
          className="w-full flex items-center justify-center space-x-2 px-4 py-2 rounded-lg bg-slate-800/30 hover:bg-slate-700/40 text-slate-300 text-sm font-medium transition-all duration-300 border border-purple-500/20 hover:border-purple-500/40"
          title="Collapse Panel"
        >
          <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 19l-7-7 7-7m8 14l-7-7 7-7" />
          </svg>
          <span>{t('analysis.collapse')}</span>
        </button>
      </div>

      {/* Chat Sessions List */}
      <div className="flex-1 overflow-y-auto custom-scrollbar">
        {sessions.length === 0 ? (
          <div className="p-6 text-center">
            <div className="text-purple-300/60 text-sm">
              {t('analysis.noChatsYet')}
            </div>
            <div className="text-slate-400 text-xs mt-2">
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
                      ? 'bg-gradient-to-r from-purple-600/20 to-purple-800/20 border-2 border-purple-500/50 shadow-lg shadow-purple-900/30'
                      : 'bg-slate-800/20 border-2 border-transparent hover:bg-slate-700/30 hover:border-purple-500/30'
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
                        className="w-full bg-slate-900/80 border border-purple-500/50 text-white text-sm px-3 py-2 rounded-lg focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent"
                        autoFocus
                      />
                    </div>
                  ) : (
                    <div
                      onClick={() => onSelectSession(session.id)}
                      className="w-full p-3 text-left flex justify-between items-start cursor-pointer"
                    >
                      <div className="flex-1 min-w-0">
                        <div className={`text-sm font-medium truncate flex items-center ${
                          session.id === currentSessionId ? 'text-purple-200' : 'text-slate-200'
                        }`}>
                          {session.title}
                        </div>
                        <div className="flex items-center space-x-2 mt-1">
                          <div className="text-xs text-slate-400">
                            {new Date(session.updatedAt).toLocaleDateString()}
                          </div>
                          {session.messages.length > 0 && (
                            <div className="text-xs text-purple-400/60">
                              • {session.messages.length} msg{session.messages.length !== 1 ? 's' : ''}
                            </div>
                          )}
                        </div>
                      </div>

                      {/* Action buttons (visible on hover) */}
                      <div className="opacity-0 group-hover:opacity-100 flex items-center space-x-1 ml-2 transition-opacity">
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            handleStartEdit(session);
                          }}
                          className="p-1.5 text-slate-400 hover:text-purple-300 hover:bg-purple-500/20 rounded transition-colors"
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
                          className="p-1.5 text-slate-400 hover:text-red-400 hover:bg-red-500/20 rounded transition-colors"
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

      {/* Footer with session counter */}
      <div className="p-4 border-t border-purple-500/20">
        <div className="flex items-center justify-center">
          <div className="text-slate-400 text-xs flex items-center space-x-2">
            <svg className="w-4 h-4 text-purple-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" />
            </svg>
            <span>
              {t('analysis.chatCount', { count: sessions.length })}
            </span>
          </div>
        </div>
      </div>

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
    </div>
  );
};

export default ChatSidebar;
