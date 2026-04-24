'use client';

import React, { useEffect, useCallback, useState, useMemo } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@clerk/nextjs';
import Link from 'next/link';
import { useSubscription } from '@/hooks/useSubscription';
import { useCoachBoard } from '@/hooks/useCoachBoard';
import CoachBoard from '@/components/coach/CoachBoard';
import CoachChat from '@/components/coach/CoachChat';
import LoadingScreen from '@/components/LoadingScreen';
import UpgradePrompt from '@/components/UpgradePrompt';
import type { BoardAction } from '@/types/coach';

export default function CoachPage() {
  const { isSignedIn, isLoaded } = useAuth();
  const subscription = useSubscription();
  const router = useRouter();
  const [sessionId, setSessionId] = useState<string | null>(null);

  const board = useCoachBoard();

  // Responsive board sizing
  const [windowWidth, setWindowWidth] = useState(typeof window !== 'undefined' ? window.innerWidth : 1024);

  useEffect(() => {
    const onResize = () => setWindowWidth(window.innerWidth);
    window.addEventListener('resize', onResize);
    return () => window.removeEventListener('resize', onResize);
  }, []);

  const snapTo8 = (size: number) => Math.floor(size / 8) * 8;

  const responsiveBoardSize = useMemo(() => {
    if (windowWidth < 400) return snapTo8(windowWidth - 8);
    if (windowWidth < 600) return snapTo8(windowWidth - 12);
    if (windowWidth < 768) return snapTo8(Math.min(windowWidth - 24, 440));
    if (windowWidth < 1024) return snapTo8(Math.min(windowWidth - 48, 500));
    return 520;
  }, [windowWidth]);

  // Redirect unauthenticated users to sign-in
  useEffect(() => {
    if (isLoaded && !isSignedIn) {
      router.push('/sign-in');
    }
  }, [isLoaded, isSignedIn, router]);

  // Handle board actions from chat
  const handleBoardActions = useCallback(
    (actions: BoardAction[]) => {
      board.applyBoardActions(actions);
    },
    [board.applyBoardActions]
  );

  // Keyboard shortcuts
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Ignore if user is typing in an input
      const tag = (e.target as HTMLElement).tagName;
      if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return;

      switch (e.key) {
        case 'ArrowLeft':
          e.preventDefault();
          board.prevMove();
          break;
        case 'ArrowRight':
          e.preventDefault();
          board.nextMove();
          break;
        case 'Home':
          e.preventDefault();
          board.firstMove();
          break;
        case 'End':
          e.preventDefault();
          board.lastMove();
          break;
        case 'f':
        case 'F':
          e.preventDefault();
          board.applyBoardAction({ type: 'flip_board' });
          break;
        case 'Escape':
          if (board.puzzleMode) {
            e.preventDefault();
            board.resetBoard();
          }
          break;
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [board]);

  // Load session from localStorage on mount
  useEffect(() => {
    const saved = localStorage.getItem('coach-session-id');
    if (saved) setSessionId(saved);
  }, []);

  // Save session to localStorage
  const handleSessionCreated = useCallback((id: string) => {
    setSessionId(id);
    localStorage.setItem('coach-session-id', id);
  }, []);

  if (!isLoaded || subscription.loading) {
    return <LoadingScreen isVisible={true} />;
  }

  if (!isSignedIn) {
    return null; // Will redirect via useEffect
  }

  if (!subscription.active) {
    return <UpgradePrompt feature="AI Chess Coach" />;
  }

  return (
    <div className="h-screen flex flex-col">
      {/* Header */}
      <header className="flex items-center justify-between px-4 py-2 border-b border-white/10">
        <div className="flex items-center gap-3">
          <Link
            href="/dashboard"
            className="text-gray-400 hover:text-white transition-colors"
            title="Back to dashboard"
          >
            <svg width="20" height="20" viewBox="0 0 20 20" fill="currentColor">
              <path
                fillRule="evenodd"
                d="M17 10a.75.75 0 01-.75.75H5.612l4.158 3.96a.75.75 0 11-1.04 1.08l-5.5-5.25a.75.75 0 010-1.08l5.5-5.25a.75.75 0 111.04 1.08L5.612 9.25H16.25A.75.75 0 0117 10z"
              />
            </svg>
          </Link>
          <h1 className="text-lg font-semibold text-white">AI Coach</h1>
          {board.puzzleMode && (
            <span className="text-xs px-2 py-0.5 bg-yellow-500/20 text-yellow-400 rounded">
              Puzzle Mode
            </span>
          )}
        </div>
        <button
          onClick={() => {
            board.resetBoard();
            setSessionId(null);
            localStorage.removeItem('coach-session-id');
          }}
          className="text-sm text-gray-400 hover:text-white transition-colors"
        >
          New session
        </button>
      </header>

      {/* Main content: Board + Chat split */}
      <div className="flex-1 flex flex-col lg:flex-row overflow-hidden">
        {/* Board panel */}
        <div className="lg:w-[55%] flex items-center justify-center p-2 sm:p-4">
          <CoachBoard
            fen={board.fen}
            arrows={board.arrows}
            highlights={board.highlights}
            orientation={board.orientation}
            puzzleMode={board.puzzleMode}
            puzzleState={board.puzzleState}
            moveIndex={board.moveIndex}
            pgnLength={board.pgn ? board.moveIndex + 1 : 0}
            onMove={board.setFenFromMove}
            onFirst={board.firstMove}
            onPrev={board.prevMove}
            onNext={board.nextMove}
            onLast={board.lastMove}
            onFlip={() => board.applyBoardAction({ type: 'flip_board' })}
            onPuzzleMove={board.validatePuzzleMove}
            boardSize={responsiveBoardSize}
          />
        </div>

        {/* Chat panel */}
        <div className="lg:w-[45%] border-t lg:border-t-0 lg:border-l border-white/10 flex flex-col min-h-0">
          <CoachChat
            currentFen={board.fen}
            sessionId={sessionId}
            onBoardActions={handleBoardActions}
            onSessionCreated={handleSessionCreated}
          />
        </div>
      </div>
    </div>
  );
}
