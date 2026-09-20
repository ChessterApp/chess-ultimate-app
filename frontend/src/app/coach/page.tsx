'use client';

import React, { useEffect, useCallback, useState, useMemo, useRef } from 'react';
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
import CoachSessions from '@/components/coach/CoachSessions';
import { coachApi, type BoardRecord } from '@/lib/coach/boards-api';

/** Rebuild an OpenedGame tab from a persisted master_game board. */
function openedGameFromBoard(b: BoardRecord): OpenedGame | null {
  if (b.kind !== 'master_game' || !b.pgn) return null;
  const src = (b.source ?? {}) as Record<string, unknown>;
  let parsed: ReturnType<typeof parseGamePgn>;
  try {
    parsed = parseGamePgn(b.pgn);
  } catch {
    return null;
  }
  return {
    id: b.id,
    white: String(src.white ?? b.title.split(' vs ')[0] ?? ''),
    black: String(src.black ?? b.title.split(' vs ')[1] ?? ''),
    whiteElo: typeof src.white_elo === 'number' ? src.white_elo : undefined,
    blackElo: typeof src.black_elo === 'number' ? src.black_elo : undefined,
    result: String(src.result ?? ''),
    eco: typeof src.eco === 'string' ? src.eco : undefined,
    date: typeof src.date === 'string' ? src.date : undefined,
    event: typeof src.event === 'string' ? src.event : undefined,
    pgn: b.pgn,
    moves: parsed.moves,
    fens: parsed.fens,
    startingFen: parsed.startingFen,
    source: 'twic',
  };
}

export default function CoachPage() {
  const { isSignedIn, isLoaded, getToken } = useAuth();
  const subscription = useSubscription();
  const router = useRouter();
  const t = useTranslations('coach');
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [sessionsOpen, setSessionsOpen] = useState(false);
  // Server-side board (tab) ids: the study board the hook renders, and the
  // master-game tabs keyed by their board id. Restored from Hermes on load.
  const [studyBoardId, setStudyBoardId] = useState<string | null>(null);
  const restoredSessionRef = useRef<string | null>(null);

  const board = useCoachBoard();

  // Game tabs state (ids are server board ids)
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

  // Handle board actions from chat. Actions addressed to a master-game tab
  // (board_id) only navigate that tab; everything else goes to the study
  // board, which the server keeps in step (see Session.apply_board_actions).
  const handleBoardActions = useCallback(
    (actions: BoardAction[]) => {
      const forStudy: BoardAction[] = [];
      for (const action of actions) {
        const target = action.board_id;
        const tab = target ? openedGames.find((g) => g.id === target) : undefined;
        if (tab && action.type === 'navigate') {
          setGameMoveIndices((prev) => {
            const cur = prev[tab.id] ?? -1;
            const last = tab.moves.length - 1;
            const next =
              action.direction === 'first' ? -1
              : action.direction === 'last' ? last
              : action.direction === 'prev' ? Math.max(-1, cur - 1)
              : Math.min(last, cur + 1);
            return { ...prev, [tab.id]: next };
          });
          setActiveGameId(tab.id);
        } else if (tab) {
          // A position change on a game tab: show it on the study board.
          setActiveGameId(null);
          forStudy.push(action);
        } else {
          forStudy.push(action);
        }
      }
      if (forStudy.length) {
        board.applyBoardActions(forStudy);
        setActiveGameId(null);
        // Actions the coach produced arrive stamped with board_id and are
        // already applied to the server board; a pasted PGN / FEN (no id)
        // must be persisted from here or a reload would lose the game.
        if (sessionId && studyBoardId) {
          for (const a of forStudy) {
            if (a.board_id) continue;
            if (a.type === 'load_pgn') void coachApi.updateBoard(sessionId, studyBoardId, { pgn: a.pgn });
            else if (a.type === 'set_fen') void coachApi.updateBoard(sessionId, studyBoardId, { fen: a.fen });
          }
        }
      }
    },
    [board.applyBoardActions, openedGames, sessionId, studyBoardId]
  );

  // The coach's actions may switch the active board server-side.
  const handleActiveBoardChanged = useCallback(
    (id: string) => {
      setActiveGameId(openedGames.some((g) => g.id === id) ? id : null);
    },
    [openedGames]
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

  // Restore the session's boards from the server: the study board's position,
  // history and orientation, and every master-game tab. Runs once per session
  // id; a session that no longer exists is forgotten.
  useEffect(() => {
    if (!sessionId || restoredSessionRef.current === sessionId) return;
    restoredSessionRef.current = sessionId;
    let cancelled = false;
    void (async () => {
      const data = await coachApi.listBoards(sessionId);
      if (cancelled) return;
      if (!data) {
        // 404 (deleted / unknown session) or Hermes down: start clean.
        localStorage.removeItem('coach-session-id');
        setSessionId(null);
        restoredSessionRef.current = null;
        return;
      }
      const study = data.boards.find((b) => b.kind === 'study' || b.kind === 'puzzle') ?? data.boards[0];
      const games: OpenedGame[] = [];
      const indices: Record<string, number> = {};
      for (const b of data.boards) {
        if (b.id === study?.id) continue;
        const g = openedGameFromBoard(b);
        if (g) {
          games.push(g);
          indices[g.id] = b.ply - 1; // viewer index: -1 = start position
        }
      }
      setOpenedGames(games);
      setGameMoveIndices(indices);

      if (study) {
        setStudyBoardId(study.id);
        board.resetBoard();
        if (study.puzzle?.solution && study.puzzle.fen) {
          board.applyBoardAction({ type: 'set_puzzle', fen: study.puzzle.fen, solution: study.puzzle.solution });
        } else if (study.pgn) {
          board.applyBoardAction({ type: 'load_pgn', pgn: study.pgn });
          board.goToMove(study.ply);
        } else if (study.fen) {
          board.applyBoardAction({ type: 'set_fen', fen: study.fen });
        }
        board.setOrientation(study.orientation);
        if (study.annotations?.arrows?.length) {
          board.applyBoardAction({ type: 'draw_arrows', arrows: study.annotations.arrows });
        }
        if (study.annotations?.highlights?.length) {
          board.applyBoardAction({
            type: 'highlight_squares',
            squares: study.annotations.highlights,
            color: study.annotations.highlight_color ?? 'yellow',
          });
        }
      }
      setActiveGameId(
        data.active_board_id && games.some((g) => g.id === data.active_board_id) ? data.active_board_id : null,
      );
    })();
    return () => {
      cancelled = true;
    };
    // board callbacks are stable (useCallback) — only the session id drives this.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId]);

  // Keep the study board's position on the server (debounced) so a reload
  // shows what the student was looking at even without a chat turn.
  const lastSyncedFenRef = useRef<string | null>(null);
  useEffect(() => {
    if (!sessionId || !studyBoardId) return;
    if (lastSyncedFenRef.current === null) {
      lastSyncedFenRef.current = board.fen; // first render after restore: nothing to sync
      return;
    }
    if (lastSyncedFenRef.current === board.fen) return;
    const fen = board.fen;
    const timer = setTimeout(() => {
      lastSyncedFenRef.current = fen;
      void coachApi.updateBoard(sessionId, studyBoardId, { position: fen });
    }, 700);
    return () => clearTimeout(timer);
  }, [board.fen, sessionId, studyBoardId]);

  // Switch to another saved session (from the sessions panel).
  const handleSelectSession = useCallback(
    (id: string) => {
      if (id === sessionId) return;
      board.resetBoard();
      setOpenedGames([]);
      setGameMoveIndices({});
      setActiveGameId(null);
      setStudyBoardId(null);
      lastSyncedFenRef.current = null;
      handleSessionCreated(id);
    },
    [sessionId, board, handleSessionCreated]
  );

  const handleNewSession = useCallback(() => {
    board.resetBoard();
    setOpenedGames([]);
    setGameMoveIndices({});
    setActiveGameId(null);
    setStudyBoardId(null);
    lastSyncedFenRef.current = null;
    restoredSessionRef.current = null;
    setSessionId(null);
    localStorage.removeItem('coach-session-id');
  }, [board]);

  // Active game derived from state
  const activeGame = useMemo(
    () => openedGames.find((g) => g.id === activeGameId) ?? null,
    [openedGames, activeGameId]
  );

  // Open a game from chat results as a tab (persisted as a master_game board)
  const handleOpenGame = useCallback(async (game: GameResult) => {
    // If already open, just switch to that tab
    const existing = openedGames.find((g) => g.source === 'twic' && g.white === game.white_name && g.black === game.black_name && g.date === game.date);
    if (existing) {
      setActiveGameId(existing.id);
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

      let boardId = `local-${game.id}`;
      if (sessionId) {
        const created = await coachApi.createBoard(sessionId, {
          kind: 'master_game',
          title: `${game.white_name} vs ${game.black_name}`,
          pgn: data.pgn,
          ply: 0,
          source: {
            twic_game_id: game.id,
            white: game.white_name,
            black: game.black_name,
            white_elo: game.white_elo,
            black_elo: game.black_elo,
            result: game.result,
            eco: game.eco,
            date: game.date,
            event: game.event,
          },
          activate: true,
        });
        if (created) boardId = created.id;
      }
      const gameIdStr = boardId;

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
  }, [openedGames, getToken, sessionId]);

  // Close a game tab
  const handleCloseGame = useCallback((gameId: string) => {
    setOpenedGames((prev) => prev.filter((g) => g.id !== gameId));
    setGameMoveIndices((prev) => {
      const next = { ...prev };
      delete next[gameId];
      return next;
    });
    if (activeGameId === gameId) setActiveGameId(null);
    if (sessionId && !gameId.startsWith('local-')) void coachApi.deleteBoard(sessionId, gameId);
  }, [activeGameId, sessionId]);

  // Tell the server which tab is active; the coach's next turn targets it.
  const selectTab = useCallback(
    (gameId: string | null) => {
      setActiveGameId(gameId);
      const boardId = gameId ?? studyBoardId;
      if (sessionId && boardId && !boardId.startsWith('local-')) {
        void coachApi.updateSession(sessionId, { active_board_id: boardId });
      }
    },
    [sessionId, studyBoardId]
  );

  // Persist a game tab's ply (debounced) so reopening lands on the same move.
  useEffect(() => {
    if (!sessionId || !activeGameId || activeGameId.startsWith('local-')) return;
    const idx = gameMoveIndices[activeGameId];
    if (idx === undefined) return;
    const timer = setTimeout(() => {
      void coachApi.updateBoard(sessionId, activeGameId, { ply: idx + 1 });
    }, 700);
    return () => clearTimeout(timer);
  }, [gameMoveIndices, activeGameId, sessionId]);

  const activeBoardId = activeGameId ?? studyBoardId;

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
        <div className="relative flex items-center gap-3">
          <button
            onClick={() => setSessionsOpen((v) => !v)}
            className="text-sm text-gray-400 hover:text-white transition-colors"
            aria-expanded={sessionsOpen}
          >
            {t('sessions')}
          </button>
          <button
            onClick={handleNewSession}
            className="text-sm text-gray-400 hover:text-white transition-colors"
          >
            {t('newSession')}
          </button>
          {sessionsOpen && (
            <CoachSessions
              currentSessionId={sessionId}
              onSelect={handleSelectSession}
              onNew={handleNewSession}
              onClose={() => setSessionsOpen(false)}
            />
          )}
        </div>
      </header>

      {/* Main content: Board + Chat split */}
      <div className="flex-1 flex flex-col lg:flex-row overflow-hidden">
        {/* Board panel */}
        <div className="lg:w-[55%] flex flex-col p-2 sm:p-4">
          {openedGames.length > 0 && (
            <div className="flex items-center gap-1 px-2 py-1 border-b border-white/10 overflow-x-auto">
              <button
                onClick={() => selectTab(null)}
                className={`px-3 py-1 text-xs rounded-t ${!activeGameId ? 'bg-white/10 text-white' : 'text-gray-400 hover:text-white'}`}
              >
                {t('coachBoard')}
              </button>
              {openedGames.map((game) => (
                <div key={game.id} className="flex items-center">
                  <button
                    onClick={() => selectTab(game.id)}
                    className={`px-3 py-1 text-xs rounded-t truncate max-w-[200px] ${
                      activeGameId === game.id ? 'bg-white/10 text-white' : 'text-gray-400 hover:text-white'
                    }`}
                  >
                    {game.white} vs {game.black}
                  </button>
                  <button
                    onClick={() => handleCloseGame(game.id)}
                    className="text-gray-500 hover:text-white ml-1 text-xs"
                    title={t('closeTab')}
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
                  onReset={() => setGameMoveIndices((prev) => ({ ...prev, [activeGameId]: -1 }))}
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
                onReset={board.resetBoard}
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
            currentFen={
              activeGameId && activeGame
                ? ((gameMoveIndices[activeGameId] ?? -1) === -1
                    ? activeGame.startingFen
                    : activeGame.fens[gameMoveIndices[activeGameId]])
                : board.fen
            }
            sessionId={sessionId}
            boardId={activeBoardId && !activeBoardId.startsWith('local-') ? activeBoardId : null}
            restoreHistory
            onBoardActions={handleBoardActions}
            onSessionCreated={handleSessionCreated}
            onActiveBoardChanged={handleActiveBoardChanged}
            onOpenGame={handleOpenGame}
          />
        </div>
      </div>
    </div>
  );
}
