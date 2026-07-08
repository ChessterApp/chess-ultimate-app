'use client';

import React, { useEffect, useCallback, useState, useMemo } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@clerk/nextjs';
import { useTranslations } from 'next-intl';
import Link from 'next/link';
import { useSubscription } from '@/hooks/useSubscription';
import { useCoachBoard } from '@/hooks/useCoachBoard';
import CoachBoard from '@/components/coach/CoachBoard';
import CoachChat from '@/components/coach/CoachChat';
import LoadingScreen from '@/components/LoadingScreen';
import UpgradePrompt from '@/components/UpgradePrompt';
import type { BoardAction, GameResult } from '@/types/coach';
import GameViewerPanel from '@/components/openings/GameViewerPanel';
import type { OpenedGame } from '@/components/openings/GameViewerPanel';
import { parseGamePgn } from '@/components/openings/GameViewerPanel';

export default function CoachPage() {
  const { isSignedIn, isLoaded, getToken } = useAuth();
  const subscription = useSubscription();
  const router = useRouter();
  const t = useTranslations('coach');
  const [sessionId, setSessionId] = useState<string | null>(null);

  const board = useCoachBoard();

  // Game tabs state
  const [openedGames, setOpenedGames] = useState<OpenedGame[]>([]);
  const [activeGameId, setActiveGameId] = useState<string | null>(null);
  const [gameMoveIndices, setGameMoveIndices] = useState<Record<string, number>>({});

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

  // Active game derived from state
  const activeGame = useMemo(
    () => openedGames.find((g) => g.id === activeGameId) ?? null,
    [openedGames, activeGameId]
  );

  // Open a game from chat results as a tab
  const handleOpenGame = useCallback(async (game: GameResult) => {
    const gameIdStr = String(game.id);

    // If already open, just switch to that tab
    if (openedGames.some((g) => g.id === gameIdStr)) {
      setActiveGameId(gameIdStr);
      return;
    }

    // Max 10 tabs
    if (openedGames.length >= 10) return;

    try {
      const token = await getToken();
      const res = await fetch(`/api/openings/games/${game.id}/pgn`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      const { moves, fens, startingFen } = parseGamePgn(data.pgn);

      const opened: OpenedGame = {
        id: gameIdStr,
        white: game.white_name,
        black: game.black_name,
        whiteElo: game.white_elo,
        blackElo: game.black_elo,
        result: game.result,
        eco: game.eco,
        date: game.date,
        event: game.event,
        pgn: data.pgn,
        moves,
        fens,
        startingFen,
        source: 'twic',
      };

      setOpenedGames((prev) => [...prev, opened]);
      setActiveGameId(gameIdStr);
    } catch (err) {
      console.error('Failed to load game PGN:', err);
    }
  }, [openedGames, getToken]);

  // Close a game tab
  const handleCloseGame = useCallback((gameId: string) => {
    setOpenedGames((prev) => prev.filter((g) => g.id !== gameId));
    setGameMoveIndices((prev) => {
      const next = { ...prev };
      delete next[gameId];
      return next;
    });
    if (activeGameId === gameId) setActiveGameId(null);
  }, [activeGameId]);

  if (!isLoaded || subscription.loading) {
    return <LoadingScreen isVisible={true} />;
  }

  if (!isSignedIn) {
    return null; // Will redirect via useEffect
  }

  if (!subscription.active) {
    return <UpgradePrompt feature={t('feature')} />;
  }

  return (
    <div className="h-screen supports-[height:100dvh]:h-[100dvh] flex flex-col">
      {/* Header */}
      <header className="flex items-center justify-between px-4 py-2 border-b border-white/10">
        <div className="flex items-center gap-3">
          <Link
            href="/dashboard"
            className="text-gray-400 hover:text-white transition-colors"
            title={t('backToDashboard')}
          >
            <svg width="20" height="20" viewBox="0 0 20 20" fill="currentColor">
              <path
                fillRule="evenodd"
                d="M17 10a.75.75 0 01-.75.75H5.612l4.158 3.96a.75.75 0 11-1.04 1.08l-5.5-5.25a.75.75 0 010-1.08l5.5-5.25a.75.75 0 111.04 1.08L5.612 9.25H16.25A.75.75 0 0117 10z"
              />
            </svg>
          </Link>
          <h1 className="text-lg font-semibold text-white">{t('title')}</h1>
          {board.puzzleMode && (
            <span className="text-xs px-2 py-0.5 bg-yellow-500/20 text-yellow-400 rounded">
              {t('puzzleMode')}
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
          {t('newSession')}
        </button>
      </header>

      {/* Main content: Board + Chat split */}
      <div className="flex-1 flex flex-col lg:flex-row overflow-hidden">
        {/* Board panel */}
        <div className="lg:w-[55%] flex flex-col p-2 sm:p-4">
          {openedGames.length > 0 && (
            <div className="flex items-center gap-1 px-2 py-1 border-b border-white/10 overflow-x-auto">
              <button
                onClick={() => setActiveGameId(null)}
                className={`px-3 py-1 text-xs rounded-t ${!activeGameId ? 'bg-white/10 text-white' : 'text-gray-400 hover:text-white'}`}
              >
                {t('coachBoard')}
              </button>
              {openedGames.map((game) => (
                <div key={game.id} className="flex items-center">
                  <button
                    onClick={() => setActiveGameId(game.id)}
                    className={`px-3 py-1 text-xs rounded-t truncate max-w-[200px] ${
                      activeGameId === game.id ? 'bg-white/10 text-white' : 'text-gray-400 hover:text-white'
                    }`}
                  >
                    {game.white} vs {game.black}
                  </button>
                  <button
                    onClick={() => handleCloseGame(game.id)}
                    className="text-gray-500 hover:text-white ml-1 text-xs"
                  >
                    ×
                  </button>
                </div>
              ))}
            </div>
          )}
          <div className="flex-1 flex items-center justify-center">
            {activeGameId && activeGame ? (
              <div className="flex flex-col lg:flex-row items-center lg:items-start gap-2">
                <CoachBoard
                  fen={
                    (gameMoveIndices[activeGameId] ?? -1) === -1
                      ? activeGame.startingFen
                      : activeGame.fens[gameMoveIndices[activeGameId]]
                  }
                  arrows={[]}
                  highlights={[]}
                  orientation={board.orientation}
                  puzzleMode={false}
                  puzzleState={null}
                  moveIndex={gameMoveIndices[activeGameId] ?? -1}
                  pgnLength={activeGame.moves.length}
                  onMove={() => {}}
                  onFirst={() => setGameMoveIndices((prev) => ({ ...prev, [activeGameId]: -1 }))}
                  onPrev={() =>
                    setGameMoveIndices((prev) => ({
                      ...prev,
                      [activeGameId]: Math.max(-1, (prev[activeGameId] ?? -1) - 1),
                    }))
                  }
                  onNext={() =>
                    setGameMoveIndices((prev) => ({
                      ...prev,
                      [activeGameId]: Math.min(activeGame.moves.length - 1, (prev[activeGameId] ?? -1) + 1),
                    }))
                  }
                  onLast={() =>
                    setGameMoveIndices((prev) => ({
                      ...prev,
                      [activeGameId]: activeGame.moves.length - 1,
                    }))
                  }
                  onFlip={() => board.applyBoardAction({ type: 'flip_board' })}
                  onPuzzleMove={() => 'wrong' as const}
                  boardSize={responsiveBoardSize}
                />
                <div className="w-full lg:w-[280px] max-h-[150px] lg:max-h-[200px] overflow-y-auto">
                  <GameViewerPanel
                    game={activeGame}
                    currentMoveIndex={gameMoveIndices[activeGameId] ?? -1}
                    onMoveIndexChange={(idx) => setGameMoveIndices((prev) => ({ ...prev, [activeGameId]: idx }))}
                  />
                </div>
              </div>
            ) : (
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
            )}
          </div>
        </div>

        {/* Chat panel */}
        <div className="flex-1 lg:flex-none lg:w-[45%] border-t lg:border-t-0 lg:border-l border-white/10 flex flex-col min-h-0">
          <CoachChat
            currentFen={board.fen}
            sessionId={sessionId}
            onBoardActions={handleBoardActions}
            onSessionCreated={handleSessionCreated}
            onOpenGame={handleOpenGame}
          />
        </div>
      </div>
    </div>
  );
}
