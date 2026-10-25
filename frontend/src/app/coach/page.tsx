'use client';

import React, { useEffect, useCallback, useState, useMemo, useReducer, useRef } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth, useUser } from '@clerk/nextjs';
import { useTranslations } from 'next-intl';
import Link from 'next/link';
import { useSubscription } from '@/hooks/useSubscription';
import { useCoachBoard } from '@/hooks/useCoachBoard';
import useOnScreenKeyboard from '@/hooks/useOnScreenKeyboard';
import useMediaQuery from '@/hooks/useMediaQuery';
import { useChromeVisibility } from '@/components/ChromeVisibilityContext';
import CoachBoard from '@/components/coach/CoachBoard';
import CoachChat, { type CoachChatHandle } from '@/components/coach/CoachChat';
import LoadingScreen from '@/components/LoadingScreen';
import UpgradePrompt from '@/components/UpgradePrompt';
import type { BoardAction, GameResult } from '@/types/coach';
import type { OpenedGame } from '@/components/openings/GameViewerPanel';
import { parseGamePgn } from '@/components/openings/GameViewerPanel';
import CoachSessions from '@/components/coach/CoachSessions';
import PlayStrip, { PlayActionBar, PlayCoachRow, PlayStudentRow } from '@/components/coach/PlayStrip';
import CoachShell from '@/components/coach/CoachShell';
import ContextBar from '@/components/coach/ContextBar';
import MoveStrip from '@/components/coach/MoveStrip';
import PlaySetupSheet from '@/components/coach/PlaySetupSheet';
import PuzzleFlow, { usePuzzleStep } from '@/components/coach/PuzzleFlow';
import MomentsFlow, { useMomentsFlow } from '@/components/coach/MomentsFlow';
import type { ReviewMomentsSummary } from '@/lib/coach/tool-summary';
import { VerdictBadge, VerdictToast } from '@/components/coach/VerdictBadge';
import ViewerTabsSheet from '@/components/coach/ViewerTabsSheet';
import ViewerMoveList from '@/components/coach/ViewerMoveList';
import { coachApi, CoachApiError, SESSION_NOT_FOUND, type BoardRecord, type GameStateView } from '@/lib/coach/boards-api';
import { clearSessionId, loadSessionId, saveSessionId } from '@/lib/coach/session-storage';
import { coachMode, currentMode, initialCoachMode } from '@/lib/coach/coach-mode';
import { coachRemark, moveVerdict, rematchOptions, type GameStartOptions, type MoveVerdict } from '@/lib/coach/play';
import {
  applyTabActions,
  EMPTY_ANNOTATIONS,
  routeBoardActions,
  type ViewerAnnotations,
} from '@/lib/coach/route-board-actions';
import {
  MOVE_STRIP_PX,
  PLAY_COACH_MIN_PX,
  PLAY_COMPOSER_PX,
  PLAY_PEEK_PX,
  PLAY_STUDENT_ROW_PX,
  playStageCss,
  sheetReducer,
} from '@/lib/coach/sheet-detent';
import { sanMoves } from '@/lib/coach/move-strip';
import type { Key } from 'chessground/types';

/** Rebuild an OpenedGame tab from a persisted master_game board, or a finished game against the coach. */
function openedGameFromBoard(b: BoardRecord, labels: { you: string; coach: string }): OpenedGame | null {
  if (!b.pgn) return null;
  const gs = (b.game_state ?? null) as Record<string, unknown> | null;
  if (b.kind === 'game') {
    // A live game is played on the study board, not shown as a tab.
    if (!gs || gs.status !== 'finished') return null;
  } else if (b.kind !== 'master_game') {
    return null;
  }
  const src = (b.source ?? {}) as Record<string, unknown>;
  let parsed: ReturnType<typeof parseGamePgn>;
  try {
    parsed = parseGamePgn(b.pgn);
  } catch {
    return null;
  }
  if (b.kind === 'game' && gs) {
    const studentWhite = gs.student_color === 'white';
    return {
      id: b.id,
      white: studentWhite ? labels.you : labels.coach,
      black: studentWhite ? labels.coach : labels.you,
      result: String(gs.result ?? ''),
      pgn: b.pgn,
      moves: parsed.moves,
      fens: parsed.fens,
      startingFen: parsed.startingFen,
      source: 'coach_game',
    };
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
    source: typeof src.kind === 'string' ? src.kind : 'twic',
  };
}

/** A live game restored from its board record (no last move / verdict known). */
function gameViewFromBoard(b: BoardRecord): GameStateView | null {
  const gs = (b.game_state ?? null) as Record<string, unknown> | null;
  if (b.kind !== 'game' || !gs || gs.status !== 'playing') return null;
  const moves = Array.isArray(gs.moves) ? (gs.moves as string[]) : [];
  const studentColor = gs.student_color === 'black' ? 'black' : 'white';
  const whiteToMove = moves.length % 2 === 0;
  return {
    board_id: b.id,
    student_color: studentColor,
    engine_elo: typeof gs.engine_elo === 'number' ? gs.engine_elo : 1500,
    comment_mode: (gs.comment_mode as GameStateView['comment_mode']) ?? 'mistakes',
    status: 'playing',
    result: null,
    termination: null,
    winner: null,
    fen: b.fen,
    pgn: b.pgn,
    ply: moves.length,
    moves,
    student_to_move: whiteToMove === (studentColor === 'white'),
    in_check: false,
    student: null,
    engine: null,
    comment_wanted: false,
  };
}

// Piece animation on the game board (Alexander's list, 26.10, item 7): the student's move, then the engine's
// reply, each animated; the speed is the student's setting, kept in the browser.
export const ANIMATION_KEY = 'coachBoardAnimationMs';
export const DEFAULT_ANIMATION_MS = 250;
export function readAnimationMs(): number {
  if (typeof window === 'undefined') return DEFAULT_ANIMATION_MS;
  try {
    const raw = window.localStorage.getItem(ANIMATION_KEY);
    if (raw === null) return DEFAULT_ANIMATION_MS;
    const v = Number(raw);
    return Number.isFinite(v) && v >= 0 ? v : DEFAULT_ANIMATION_MS;
  } catch {
    return DEFAULT_ANIMATION_MS;
  }
}

export default function CoachPage() {
  const { isSignedIn, isLoaded, getToken, userId } = useAuth();
  const { user } = useUser();
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

  // What the board is doing (explore / play / puzzle / viewer): one reducer.
  // The viewer's tab id is the active game tab.
  const [modeState, dispatchMode] = useReducer(coachMode, initialCoachMode);
  const mode = currentMode(modeState);
  // «Моменты»: the game review being replayed on the study board (the board's own position stays underneath).
  const [review, setReview] = useState<ReviewMomentsSummary | null>(null);
  const moments = useMomentsFlow(review);
  const momentsOn = modeState.base === 'moments' && review !== null;
  const momentFen = momentsOn ? moments.board?.fen ?? null : null;
  const activeGameId = modeState.viewerId;
  const setActiveGameId = useCallback(
    (id: string | null) => dispatchMode(id ? { type: 'view_tab', id } : { type: 'view_study' }),
    [],
  );

  // Game tabs state (ids are server board ids)
  const [openedGames, setOpenedGames] = useState<OpenedGame[]>([]);
  const [gameMoveIndices, setGameMoveIndices] = useState<Record<string, number>>({});
  // The coach's arrows / highlights on each game tab (routed by board_id).
  const [tabAnnotations, setTabAnnotations] = useState<Record<string, ViewerAnnotations>>({});

  // A game against the coach, played on the study board (see PlayStrip).
  const [game, setGame] = useState<GameStateView | null>(null);
  const [gameThinking, setGameThinking] = useState(false);
  const [gameDialogOpen, setGameDialogOpen] = useState(false);
  const [gameError, setGameError] = useState<string | null>(null);
  const [lastGameOptions, setLastGameOptions] = useState<GameStartOptions | null>(null);
  // The coach's latest remark in the game, one line, for the play strip's bubble.
  const [coachLine, setCoachLine] = useState<string | null>(null);
  const [verdictToast, setVerdictToast] = useState<MoveVerdict | null>(null);
  // The composer is swapped for the game's action bar; «Чат» brings it back.
  const [playChatOpen, setPlayChatOpen] = useState(false);
  const gameRef = useRef<GameStateView | null>(null);
  const [animationMs, setAnimationMs] = useState<number>(DEFAULT_ANIMATION_MS);
  const animationMsRef = useRef(animationMs);
  animationMsRef.current = animationMs;
  useEffect(() => { setAnimationMs(readAnimationMs()); }, []);
  const animTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  // The earlier position of the game the student browsed to with the move buttons (26.10): the game itself
  // goes on; a move by hand is not taken there; the coach is told what is shown.
  const viewPly = game && game.status === 'playing' && board.fens.length > 1 && board.moveIndex >= 0 && board.moveIndex < board.fens.length - 1
    ? board.moveIndex : null;
  const viewPlyRef = useRef<number | null>(viewPly);
  viewPlyRef.current = viewPly;
  // applyGameView, for the board actions handled above it (a `game` action from the coach).
  const applyGameViewRef = useRef<((view: GameStateView) => void) | null>(null);
  gameRef.current = game;
  const gameLive = game?.status === 'playing';
  const chatRef = useRef<CoachChatHandle>(null);

  // ≥ 1024px keeps the split desktop layout (P4 redesigns it); below it the
  // immersive CoachShell, sized by CSS alone. Only the media query is read.
  const isDesktop = useMediaQuery('(min-width: 1024px)');

  // The coach is a focus mode on phones: no app NavBar or bottom tab bar while
  // it is open, exit with ✕ (both bars are md:hidden — the desktop is untouched).
  const keyboard = useOnScreenKeyboard();
  const { setChromeHidden } = useChromeVisibility();
  useEffect(() => {
    setChromeHidden(true);
    return () => setChromeHidden(false);
  }, [setChromeHidden]);

  // The mobile coach sheet: peek / half / full (see lib/coach/sheet-detent.ts).
  const [sheetDetent, dispatchSheet] = useReducer(sheetReducer, 'peek');
  // A game, a puzzle or a viewed game starting (or ending) shows the board.
  useEffect(() => dispatchSheet({ type: 'mode_changed' }), [mode]);
  const [tabsOpen, setTabsOpen] = useState(false);

  const snapTo8 = (size: number) => Math.floor(size / 8) * 8;

  // Beside the chat the board gets 55% of what the sidebar leaves, so on a
  // desktop its size follows that area, not the window: a fixed 520 px board
  // (and a 520 + 280 px game view) overflowed it under the sidebar and the
  // chat on laptops (live site, 2026-09-29).
  const [boardArea, setBoardArea] = useState({ width: 0, height: 0 });
  const boardAreaObserver = useRef<ResizeObserver | null>(null);
  const measureBoardArea = useCallback((el: HTMLDivElement | null) => {
    boardAreaObserver.current?.disconnect();
    boardAreaObserver.current = null;
    if (!el || typeof ResizeObserver === 'undefined') return;
    const measure = () => {
      if (el.clientWidth > 0) setBoardArea({ width: el.clientWidth, height: el.clientHeight });
    };
    measure();
    boardAreaObserver.current = new ResizeObserver(measure);
    boardAreaObserver.current.observe(el);
  }, []);
  // Height the mode's strip takes under the board (moves, play rows, step panel).
  // «Моменты» sit in the chat column's footer, not under the board.
  const below = mode === 'viewer' ? 52 : mode === 'play' ? 190 : mode === 'puzzle' ? 170 : 0;

  // Desktop: the mode's strip renders under the board too.
  const responsiveBoardSize = useMemo(() => {
    if (!boardArea.width) return 520;
    const byHeight = boardArea.height ? boardArea.height - 44 - below : 520;
    return snapTo8(Math.max(280, Math.min(520, boardArea.width - 8, byHeight)));
  }, [boardArea.width, boardArea.height, below]);

  // An opened master game: the move list sits beside the board when the board
  // keeps at least MIN_BESIDE px that way, else under it — with the board sized
  // so board, controls and list fit the height.
  const gameLayout = useMemo(() => {
    const PANEL = 220;
    const GAP = 8;
    const CONTROLS = 56;
    const LIST = 150;
    const MIN_BESIDE = 440;
    if (!boardArea.width) return { beside: true, size: responsiveBoardSize, panelWidth: PANEL };
    const besideSize = Math.min(520, boardArea.width - PANEL - GAP, boardArea.height - CONTROLS - GAP);
    if (besideSize >= MIN_BESIDE) {
      return { beside: true, size: snapTo8(besideSize), panelWidth: PANEL };
    }
    const underSize = Math.min(520, boardArea.width - GAP, boardArea.height - CONTROLS - LIST - 2 * GAP);
    const size = snapTo8(Math.max(280, underSize));
    return { beside: false, size, panelWidth: size };
  }, [boardArea.width, boardArea.height, responsiveBoardSize]);

  // Redirect unauthenticated users to sign-in
  useEffect(() => {
    if (isLoaded && !isSignedIn) {
      router.push('/sign-in');
    }
  }, [isLoaded, isSignedIn, router]);

  // Handle board actions from chat. Actions addressed to a master-game tab
  // (board_id) navigate it or draw on it; everything else goes to the study
  // board, which the server keeps in step (see Session.apply_board_actions).
  const handleBoardActions = useCallback(
    (incoming: BoardAction[]) => {
      // The board shows another position of the game against the coach (game_view, 26.10): browsed, not played.
      for (const a of incoming) {
        if (a.type !== 'game_view') continue;
        if (a.ply === null) board.lastMove();
        else board.goToMove(a.ply);
      }
      const actions = incoming.filter((a) => a.type !== 'game_view');
      const routed = routeBoardActions(actions, openedGames.map((g) => g.id));
      // A game the coach started or moved on (start_game / make_game_move, text or voice): shown
      // exactly as a game started with the button (2026-10-12).
      if (routed.game) applyGameViewRef.current?.(routed.game);
      for (const [id, tabActions] of Object.entries(routed.tabs)) {
        const last = (openedGames.find((g) => g.id === id)?.moves.length ?? 0) - 1;
        setGameMoveIndices((prev) => ({
          ...prev,
          [id]: applyTabActions({ index: prev[id] ?? -1, annotations: EMPTY_ANNOTATIONS }, tabActions, last).index,
        }));
        setTabAnnotations((prev) => ({
          ...prev,
          [id]: applyTabActions({ index: -1, annotations: prev[id] ?? EMPTY_ANNOTATIONS }, tabActions, last).annotations,
        }));
      }
      if (routed.focusTab) setActiveGameId(routed.focusTab);
      const forStudy = routed.study;
      if (forStudy.length) {
        // While a game is on, the study board IS the game: the coach may draw
        // on it but never change the position under the student.
        const live = gameRef.current?.status === 'playing';
        const allowed = live
          ? forStudy.filter((a) => a.type === 'draw_arrows' || a.type === 'highlight_squares' || a.type === 'flip_board')
          : forStudy;
        if (!allowed.length) return;
        board.applyBoardActions(allowed);
        setActiveGameId(null);
        if (live) return;
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
    [board, openedGames, sessionId, studyBoardId, setActiveGameId]
  );

  // The coach's actions may switch the active board server-side.
  const handleActiveBoardChanged = useCallback(
    (id: string) => {
      setActiveGameId(openedGames.some((g) => g.id === id) ? id : null);
    },
    [openedGames, setActiveGameId]
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

  // Load the signed-in user's session from localStorage. The restore waits for
  // the subscription check, so a paywalled visit never calls Hermes.
  const canUseCoach = !!userId && !subscription.loading && subscription.active;
  useEffect(() => {
    if (!canUseCoach || !userId) return;
    const saved = loadSessionId(userId);
    if (saved) setSessionId(saved);
  }, [canUseCoach, userId]);

  // Save session to localStorage
  const handleSessionCreated = useCallback(
    (id: string) => {
      setSessionId(id);
      if (userId) saveSessionId(userId, id);
    },
    [userId],
  );

  // Restore the session's boards from the server: the study board's position,
  // history and orientation, and every master-game tab. Runs once per session
  // id. Only Hermes's own "Session not found" forgets the id — a session that
  // is gone or belongs to another account. Any other failure keeps it: a
  // Hermes without the boards API (404) or a hiccup must not wipe the chat, as
  // it did right after the first answer on the live site (2026-09-25).
  useEffect(() => {
    if (!sessionId || restoredSessionRef.current === sessionId) return;
    restoredSessionRef.current = sessionId;
    let cancelled = false;
    void (async () => {
      const data = await coachApi.listBoards(sessionId);
      if (cancelled || !data) return;
      if (data === SESSION_NOT_FOUND) {
        restoredSessionRef.current = null;
        setSessionId((current) => (current === sessionId ? null : current));
        if (userId) clearSessionId(userId);
        return;
      }
      const study = data.boards.find((b) => b.kind === 'study' || b.kind === 'puzzle') ?? data.boards[0];
      const games: OpenedGame[] = [];
      const indices: Record<string, number> = {};
      const annotations: Record<string, ViewerAnnotations> = {};
      const labels = { you: t('youLabel'), coach: t('coachLabel') };
      for (const b of data.boards) {
        if (b.id === study?.id) continue;
        const g = openedGameFromBoard(b, labels);
        if (g) {
          games.push(g);
          indices[g.id] = b.ply - 1; // viewer index: -1 = start position
          annotations[g.id] = { arrows: b.annotations?.arrows ?? [], highlights: b.annotations?.highlights ?? [] };
        }
      }
      setOpenedGames(games);
      setGameMoveIndices(indices);
      setTabAnnotations(annotations);

      // A game in progress comes back onto the study board, student's colour up.
      const liveBoard = data.boards.find((b) => gameViewFromBoard(b) !== null);
      const liveGame = liveBoard ? gameViewFromBoard(liveBoard) : null;

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
      if (liveGame) {
        setGame(liveGame);
        dispatchMode({ type: 'game_started' });
        board.resetBoard();
        if (liveGame.pgn) board.applyBoardAction({ type: 'load_pgn', pgn: liveGame.pgn });
        board.setOrientation(liveGame.student_color);
        setActiveGameId(null);
      } else {
        setGame(null);
        dispatchMode({ type: 'game_closed' });
        setActiveGameId(
          data.active_board_id && games.some((g) => g.id === data.active_board_id) ? data.active_board_id : null,
        );
      }
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
    if (gameLive) return; // the game endpoint persists every move itself
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
  }, [board.fen, sessionId, studyBoardId, gameLive]);

  // ── Game against the coach ─────────────────────────────────────────────
  const applyGameView = useCallback(
    (view: GameStateView) => {
      const prevMoves = gameRef.current?.moves.length ?? 0;
      setGame(view);
      setGameError(null);
      dispatchMode({ type: 'game_started' });
      if (animTimerRef.current) { clearTimeout(animTimerRef.current); animTimerRef.current = null; }
      if (view.pgn) {
        board.applyBoardAction({ type: 'load_pgn', pgn: view.pgn });
        const total = view.moves.length;
        if (animationMsRef.current > 0 && total - prevMoves === 2 && view.student && view.engine) {
          // The student's move first, the engine's reply after it has been seen (26.10): two moves, not one jump.
          board.goToMove(total - 1);
          animTimerRef.current = setTimeout(() => {
            animTimerRef.current = null;
            board.goToMove(total);
          }, animationMsRef.current + 150);
        }
      } else board.applyBoardAction({ type: 'set_fen', fen: view.fen });
      board.setOrientation(view.student_color);
    },
    [board],
  );
  applyGameViewRef.current = applyGameView;

  const requestGameComment = useCallback(
    (sid: string, view: GameStateView) => {
      void chatRef.current?.streamAssistant(
        `/api/coach/sessions/${encodeURIComponent(sid)}/game/${encodeURIComponent(view.board_id)}/comment`,
        { event: view.status === 'finished' ? 'end' : 'move' },
      );
    },
    [],
  );

  const handleStartGame = useCallback(
    async (options: GameStartOptions) => {
      setGameThinking(true);
      try {
        let sid = sessionId;
        if (!sid) {
          const created = await coachApi.createSession();
          if (!created) throw new Error('session');
          sid = created.id;
          handleSessionCreated(sid);
        }
        const view = await coachApi.startGame(sid, options);
        if (!view) throw new Error('start');
        setLastGameOptions(options);
        setGameDialogOpen(false);
        setCoachLine(null);
        setVerdictToast(null);
        setPlayChatOpen(false);
        board.resetBoard();
        applyGameView(view);
      } catch (err: unknown) {
        const reason = err instanceof Error ? err.message : 'unknown';
        setGameError(t('gameStartFailed', { reason }));
      } finally {
        setGameThinking(false);
      }
    },
    [sessionId, handleSessionCreated, board, applyGameView, t],
  );

  const submitGameMove = useCallback(
    async (uci: string) => {
      const current = gameRef.current;
      if (!sessionId || !current || current.status !== 'playing') return;
      setGameThinking(true);
      try {
        const view = await coachApi.gameMove(sessionId, current.board_id, uci);
        applyGameView(view);
        setVerdictToast(moveVerdict(view.student));
        // The voice pipeline says the move and the reply at once and then reads the coach's comment (26.10).
        chatRef.current?.announceGame(view);
        if (view.comment_wanted || chatRef.current?.voicePipelineOn()) requestGameComment(sessionId, view);
      } catch (err: unknown) {
        const reason = err instanceof CoachApiError ? err.message : err instanceof Error ? err.message : 'unknown';
        setGameError(t('gameMoveFailed', { reason }));
      } finally {
        setGameThinking(false);
      }
    },
    [sessionId, applyGameView, requestGameComment, t],
  );

  // A move on the study board: the game's move while a game is on, otherwise
  // the free study move the hook already handles.
  const handleStudyMove = useCallback(
    (from: string, to: string, promotion?: 'q' | 'r' | 'b' | 'n') => {
      const current = gameRef.current;
      if (current && current.status === 'playing') {
        if (!current.student_to_move || gameThinking) return;
        if (viewPlyRef.current !== null) return;  // browsing an earlier position: the game is not changed by a move there
        void submitGameMove(`${from}${to}${promotion ?? ''}`);
        return;
      }
      board.setFenFromMove(from as Parameters<typeof board.setFenFromMove>[0], to as Parameters<typeof board.setFenFromMove>[1], promotion);
    },
    [board, gameThinking, submitGameMove],
  );

  const handleGameTakeback = useCallback(async () => {
    if (!sessionId || !game) return;
    const view = await coachApi.gameTakeback(sessionId, game.board_id);
    if (view) applyGameView(view);
  }, [sessionId, game, applyGameView]);

  const handleGameContinue = useCallback(async () => {
    const current = gameRef.current;
    const ply = viewPlyRef.current;
    if (!sessionId || !current || ply === null) return;
    setGameThinking(true);
    try {
      const view = await coachApi.gameContinue(sessionId, current.board_id, ply);
      applyGameView(view);
      chatRef.current?.announceGame(view);
    } catch (err: unknown) {
      const reason = err instanceof CoachApiError ? err.message : err instanceof Error ? err.message : 'unknown';
      setGameError(t('gameMoveFailed', { reason }));
    } finally {
      setGameThinking(false);
    }
  }, [sessionId, applyGameView, t]);

  const handleGameResign = useCallback(async () => {
    if (!sessionId || !game) return;
    const view = await coachApi.gameResign(sessionId, game.board_id);
    if (view) {
      applyGameView(view);
      requestGameComment(sessionId, view);
    }
  }, [sessionId, game, applyGameView, requestGameComment]);

  const handleGameClose = useCallback(() => {
    setGame(null);
    setGameError(null);
    setCoachLine(null);
    setVerdictToast(null);
    dispatchMode({ type: 'game_closed' });
    if (sessionId && studyBoardId) void coachApi.updateSession(sessionId, { active_board_id: studyBoardId });
  }, [sessionId, studyBoardId]);

  // Switch to another saved session (from the sessions panel).
  const handleSelectSession = useCallback(
    (id: string) => {
      if (id === sessionId) return;
      board.resetBoard();
      setOpenedGames([]);
      setGameMoveIndices({});
      setTabAnnotations({});
      dispatchMode({ type: 'reset' });
      setStudyBoardId(null);
      setGame(null);
      lastSyncedFenRef.current = null;
      handleSessionCreated(id);
    },
    [sessionId, board, handleSessionCreated]
  );

  const handleNewSession = useCallback(() => {
    board.resetBoard();
    setGame(null);
    setOpenedGames([]);
    setGameMoveIndices({});
    setTabAnnotations({});
    dispatchMode({ type: 'reset' });
    setStudyBoardId(null);
    lastSyncedFenRef.current = null;
    restoredSessionRef.current = null;
    setSessionId(null);
    if (userId) clearSessionId(userId);
  }, [board, userId]);

  // Active game derived from state
  const activeGame = useMemo(
    () => openedGames.find((g) => g.id === activeGameId) ?? null,
    [openedGames, activeGameId]
  );

  // The position the chat asks about: the open master game's current move, else the board.
  const chatFen = momentFen
    ? momentFen
    : activeGameId && activeGame
      ? (gameMoveIndices[activeGameId] ?? -1) === -1
        ? activeGame.startingFen
        : activeGame.fens[gameMoveIndices[activeGameId]]
      : board.fen;

  // Warm Hermes' analysis of that position while the student looks at it, so a
  // question about it starts from Stockfish's result. Not during a live game:
  // the coach hints there and gets no engine line.
  useEffect(() => {
    if (gameLive || !chatFen) return;
    const timer = setTimeout(() => coachApi.prewarmEngine(chatFen), 500);
    return () => clearTimeout(timer);
  }, [chatFen, gameLive]);

  // Open a game from chat results as a tab (persisted as a master_game board)
  const handleOpenGame = useCallback(async (game: GameResult) => {
    // If already open, just switch to that tab. A TWIC card is recognised by its
    // players and date; an own / imported card (it carries the PGN) by the PGN.
    const source = game.source ?? 'twic';
    const existing = source === 'twic'
      ? openedGames.find((g) => g.source === 'twic' && g.white === game.white_name && g.black === game.black_name && g.date === game.date)
      : openedGames.find((g) => g.source === source && g.pgn === game.pgn);
    if (existing) {
      setActiveGameId(existing.id);
      return;
    }

    // Max 10 tabs
    if (openedGames.length >= 10) return;

    try {
      let pgn = game.pgn;
      if (!pgn) {
        // Master database game: fetch the PGN by TWIC id.
        const token = await getToken();
        const res = await fetch(`/api/openings/games/${game.id}/pgn`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        pgn = data.pgn as string;
      }
      const { moves, fens, startingFen } = parseGamePgn(pgn);

      let boardId = `local-${game.id}`;
      if (sessionId) {
        const created = await coachApi.createBoard(sessionId, {
          kind: 'master_game',
          title: `${game.white_name} vs ${game.black_name}`,
          pgn,
          ply: 0,
          source: {
            kind: source,
            twic_game_id: source === 'twic' ? game.id : undefined,
            game_id: source === 'twic' ? undefined : game.id,
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
        whiteElo: game.white_elo ?? undefined,
        blackElo: game.black_elo ?? undefined,
        result: game.result,
        eco: game.eco,
        date: game.date,
        event: game.event,
        pgn,
        moves,
        fens,
        startingFen,
        source,
      };

      setOpenedGames((prev) => [...prev, opened]);
      setActiveGameId(gameIdStr);
    } catch (err) {
      console.error('Failed to load game PGN:', err);
    }
  }, [openedGames, getToken, sessionId, setActiveGameId]);

  // Close a game tab
  const handleCloseGame = useCallback((gameId: string) => {
    setOpenedGames((prev) => prev.filter((g) => g.id !== gameId));
    setGameMoveIndices((prev) => {
      const next = { ...prev };
      delete next[gameId];
      return next;
    });
    dispatchMode({ type: 'tab_closed', id: gameId });
    if (sessionId && !gameId.startsWith('local-')) void coachApi.deleteBoard(sessionId, gameId);
  }, [sessionId]);

  // Tell the server which tab is active; the coach's next turn targets it.
  const selectTab = useCallback(
    (gameId: string | null) => {
      setActiveGameId(gameId);
      const boardId = gameId ?? studyBoardId;
      if (sessionId && boardId && !boardId.startsWith('local-')) {
        void coachApi.updateSession(sessionId, { active_board_id: boardId });
      }
    },
    [sessionId, studyBoardId, setActiveGameId]
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

  // The coach's turns target the game board while a game is on (so it knows
  // the game), the tab being viewed, or the study board.
  const activeBoardId = activeGameId ?? (gameLive && game ? game.board_id : null) ?? studyBoardId;

  // A puzzle the coach sets is solved step by step (PuzzleFlow); the mode follows the board hook.
  useEffect(() => {
    dispatchMode({ type: board.puzzleMode ? 'puzzle_started' : 'puzzle_ended' });
  }, [board.puzzleMode]);
  const puzzle = usePuzzleStep(board.puzzleState, board.fen, board.validatePuzzleMove);

  const startMoments = useCallback((summary: ReviewMomentsSummary) => {
    setReview(summary);
    dispatchMode({ type: 'moments_started' });
  }, []);
  const exitMoments = useCallback(() => dispatchMode({ type: 'moments_ended' }), []);
  // Phones: a verdict opens the sheet to half so the feedback panel fits; the next moment drops it to peek.
  const momentPhase = momentsOn ? moments.state.step.phase : null;
  useEffect(() => {
    if (isDesktop || !momentPhase) return;
    if (momentPhase === 'correct' || momentPhase === 'wrong') dispatchSheet({ type: 'snap', detent: 'half' });
    else if (momentPhase === 'idle') dispatchSheet({ type: 'snap', detent: 'peek' });
  }, [momentPhase, isDesktop]);
  // The review ended, or a puzzle / game took the board: drop it.
  useEffect(() => {
    if (modeState.base !== 'moments') setReview(null);
  }, [modeState.base]);

  // The student stepping through a game tab: the coach's arrows were for another position.
  const jumpTab = useCallback((id: string, index: (prev: number) => number) => {
    setGameMoveIndices((prev) => ({ ...prev, [id]: index(prev[id] ?? -1) }));
    setTabAnnotations((prev) => (prev[id] ? { ...prev, [id]: EMPTY_ANNOTATIONS } : prev));
  }, []);

  const verdict = game?.status === 'playing' ? moveVerdict(game.student) : null;
  const clearVerdictToast = useCallback(() => setVerdictToast(null), []);
  const closeGameDialog = useCallback(() => {
    setGameDialogOpen(false);
    setGameError(null);
  }, []);
  const handleAssistantReply = useCallback((text: string) => {
    if (gameRef.current) setCoachLine(coachRemark(text) || null);
  }, []);

  // The study board's moves for the mobile move strip (the hook keeps positions).
  const studyMoves = useMemo(() => sanMoves(board.fens), [board.fens]);

  // The mobile context bar's title: the session's name, or its first question.
  // Re-read when the sessions sheet closes (it may have been renamed there).
  const [sessionTitle, setSessionTitle] = useState<string | null>(null);
  useEffect(() => {
    if (isDesktop || sessionsOpen) return;
    if (!sessionId) {
      setSessionTitle(null);
      return;
    }
    let cancelled = false;
    void coachApi.listSessions().then((list) => {
      const current = list?.find((x) => x.id === sessionId);
      if (!cancelled) setSessionTitle(current ? current.title || current.preview || null : null);
    });
    return () => {
      cancelled = true;
    };
  }, [isDesktop, sessionId, sessionsOpen]);

  if (!isLoaded || subscription.loading) {
    return <LoadingScreen isVisible={true} />;
  }

  if (!isSignedIn) {
    return null; // Will redirect via useEffect
  }

  if (!subscription.active) {
    return <UpgradePrompt feature={t('feature')} />;
  }

  const viewerAnnotations = (activeGameId && tabAnnotations[activeGameId]) || EMPTY_ANNOTATIONS;
  const onPuzzle = modeState.base === 'puzzle' && board.puzzleState !== null;

  const momentBoard = momentsOn ? moments.board : null;
  const studyBoard = (
    <CoachBoard
      fen={momentBoard ? momentBoard.fen : onPuzzle ? puzzle.boardFen : board.fen}
      arrows={momentBoard ? (momentBoard.arrows as Array<{ from: Key; to: Key; brush: string }>) : board.arrows}
      highlights={momentBoard ? (momentBoard.highlights as Key[]) : board.highlights}
      orientation={momentBoard ? momentBoard.orientation : board.orientation}
      movable={momentBoard ? momentBoard.movable : !onPuzzle || !puzzle.boardLocked}
      flash={momentsOn ? moments.flash : onPuzzle ? puzzle.flash : null}
      overlay={
        game && (
          <>
            {verdict && <VerdictBadge verdict={verdict} orientation={board.orientation} />}
            {verdictToast && <VerdictToast verdict={verdictToast} onDone={clearVerdictToast} />}
            {viewPly !== null && (
              <div className="absolute inset-x-0 bottom-0 z-10 flex items-center justify-between gap-2 bg-black/70 px-3 py-2 text-xs text-white" data-testid="game-viewing">
                <span>{t('viewingPast', { ply: viewPly, total: game.moves.length })}</span>
                <span className="flex shrink-0 gap-2">
                  <button type="button" className="rounded bg-white/15 px-2 py-1" onClick={() => void handleGameContinue()} disabled={gameThinking}>{t('continueHere')}</button>
                  <button type="button" className="rounded bg-white/15 px-2 py-1" onClick={board.lastMove}>{t('backToGame')}</button>
                </span>
              </div>
            )}
          </>
        )
      }
      animationDuration={animationMs}
      onMove={momentsOn ? moments.move : onPuzzle ? puzzle.move : handleStudyMove}
      onReset={gameLive ? () => {} : board.resetBoard}
      onFirst={board.firstMove}
      onPrev={board.prevMove}
      onNext={board.nextMove}
      onLast={board.lastMove}
      onFlip={() => board.applyBoardAction({ type: 'flip_board' })}
      // Phones: fluid — the shell's CSS sizes the board's box.
      boardSize={isDesktop ? responsiveBoardSize : undefined}
    />
  );

  const viewerTabs = openedGames.map((g) => ({
    id: g.id,
    title: `${g.white} vs ${g.black}`,
    subtitle: [g.result, g.event, g.date].filter(Boolean).join(' · '),
  }));

  const playActions = game && {
    game,
    thinking: gameThinking,
    chatOpen: playChatOpen,
    onHint: () => chatRef.current?.send(t('hintMessage')),
    onTakeback: () => void handleGameTakeback(),
    onResign: () => void handleGameResign(),
    onToggleChat: () => setPlayChatOpen((open) => !open),
    onReview: () => chatRef.current?.send(t('reviewMessage')),
    onRematch: () => void handleStartGame(rematchOptions(game, lastGameOptions)),
    onClose: handleGameClose,
    animationMs,
    onAnimationChange: (ms: number) => {
      setAnimationMs(ms);
      try { window.localStorage.setItem(ANIMATION_KEY, String(ms)); } catch { /* storage may be blocked */ }
    },
    // Browsing the game's record (item 8): the board's own history, loaded from the game's PGN.
    nav: {
      index: Math.max(0, board.moveIndex),
      total: Math.max(0, board.fens.length - 1),
      onFirst: board.firstMove,
      onPrev: board.prevMove,
      onNext: board.nextMove,
      onLast: board.lastMove,
    },
  };

  const puzzleFlow = onPuzzle && board.puzzleState && (
    <PuzzleFlow
      controls={puzzle}
      puzzle={board.puzzleState}
      onAsk={(message) => chatRef.current?.send(message)}
      onNextPuzzle={() => chatRef.current?.send(t('promptPuzzle'))}
      onExit={() => board.applyBoardAction({ type: 'set_fen', fen: board.fen })}
    />
  );

  const momentsFlow = momentsOn && (
    <MomentsFlow controls={moments} onAsk={(message) => chatRef.current?.send(message)} onExit={exitMoments} />
  );

  const gameErrorLine = gameError && !gameDialogOpen && (
    <div className="text-xs text-(--coach-danger)" role="alert" data-testid="game-error">
      {gameError}
    </div>
  );

  const playSetup = gameDialogOpen && (
    <PlaySetupSheet
      busy={gameThinking}
      initial={lastGameOptions}
      error={gameError}
      onStart={(options) => void handleStartGame(options)}
      onCancel={closeGameDialog}
    />
  );

  const coachChat = (
    <CoachChat
      ref={chatRef}
      currentFen={chatFen}
      currentPgn={board.pgn}
      sessionId={sessionId}
      boardId={activeBoardId && !activeBoardId.startsWith('local-') ? activeBoardId : null}
      restoreHistory
      onBoardActions={handleBoardActions}
      onSessionCreated={handleSessionCreated}
      onActiveBoardChanged={handleActiveBoardChanged}
      onOpenGame={handleOpenGame}
      game={game}
      viewPly={viewPly}
      composerHidden={gameLive && !playChatOpen}
      onAssistantReply={handleAssistantReply}
      // Phones: the sheet hosts the chat — its peek, the game's actions or the puzzle's steps.
      view={!isDesktop && sheetDetent === 'peek' ? 'peek' : 'thread'}
      onExpand={() => dispatchSheet({ type: 'expand' })}
      onComposerFocus={isDesktop ? undefined : () => dispatchSheet({ type: 'composer_focus' })}
      footerHugs={!isDesktop && !!playActions}
      footer={isDesktop ? momentsFlow || undefined : playActions ? <PlayActionBar {...playActions} /> : momentsFlow || puzzleFlow || undefined}
      mode={mode}
      // Phones: a card put something on the board — drop the sheet so it shows.
      onShowBoard={isDesktop ? undefined : () => dispatchSheet({ type: 'snap', detent: 'peek' })}
      onStartMoments={startMoments}
      // The empty session's home: today's plan (its «play the coach» opens the play setup).
      dailyPlan={{ greetingName: user?.firstName }}
      onPlayCoach={gameLive ? undefined : () => setGameDialogOpen(true)}
    />
  );

  if (!isDesktop) {
    const viewing = activeGameId ? activeGame : null;
    const modeLabel = {
      explore: t('modeExplore'),
      play: t('gameDialogTitle'),
      puzzle: t('puzzleTitle'),
      moments: t('momentsTitle'),
      viewer: t('modeViewer'),
    }[mode];
    const subtitle =
      openedGames.length > 0 ? `${modeLabel} · ${t('boardsCount', { count: openedGames.length + 1 })}` : modeLabel;

    let stageBoard: React.ReactNode = studyBoard;
    let above: React.ReactNode = null;
    let belowBoard: React.ReactNode = (
      <MoveStrip
        moves={studyMoves}
        currentIndex={board.moveIndex - 1}
        onJump={(i) => board.goToMove(i + 1)}
        onPrev={board.prevMove}
        onNext={board.nextMove}
      />
    );
    let stageChrome = MOVE_STRIP_PX;
    let peekPx: number | undefined;
    if (viewing && activeGameId) {
      const index = gameMoveIndices[activeGameId] ?? -1;
      stageBoard = (
        <CoachBoard
          fen={index === -1 ? viewing.startingFen : viewing.fens[index]}
          arrows={viewerAnnotations.arrows as Array<{ from: Key; to: Key; brush: string }>}
          highlights={viewerAnnotations.highlights as Key[]}
          orientation={board.orientation}
          onMove={() => {}}
          onReset={() => jumpTab(activeGameId, () => -1)}
          onFirst={() => jumpTab(activeGameId, () => -1)}
          onPrev={() => jumpTab(activeGameId, (i) => Math.max(-1, i - 1))}
          onNext={() => jumpTab(activeGameId, (i) => Math.min(viewing.moves.length - 1, i + 1))}
          onLast={() => jumpTab(activeGameId, () => viewing.moves.length - 1)}
          onFlip={() => board.applyBoardAction({ type: 'flip_board' })}
        />
      );
      belowBoard = (
        <MoveStrip
          moves={viewing.moves}
          currentIndex={index}
          onJump={(i) => jumpTab(activeGameId, () => i)}
          onPrev={() => jumpTab(activeGameId, (i) => Math.max(-1, i - 1))}
          onNext={() => jumpTab(activeGameId, (i) => Math.min(viewing.moves.length - 1, i + 1))}
        />
      );
    } else if (game) {
      // The sheet hugs the action bar (+ the composer while «Чат» is on) — measured
      // by the shell, these are the fallback; the board takes the full width and
      // the coach row the rest (see playStageCss).
      peekPx = PLAY_PEEK_PX + (playChatOpen ? PLAY_COMPOSER_PX : 0);
      above = (
        <div className="flex h-full flex-col px-2 pt-1 pb-2">
          <div className="min-h-0 flex-1">
            <PlayCoachRow
              game={game}
              thinking={gameThinking}
              comment={coachLine}
              onExpand={() => dispatchSheet({ type: 'snap', detent: 'half' })}
            />
          </div>
          {gameErrorLine}
        </div>
      );
      belowBoard = (
        <>
          {/* Tall phones: the move strip fills the slack; elsewhere its box is 0 tall. */}
          <div className="shrink-0 overflow-hidden" style={{ height: playStageCss(peekPx).moveStrip }}>
            {belowBoard}
          </div>
          <div className="flex shrink-0 flex-col justify-center px-2" style={{ height: PLAY_STUDENT_ROW_PX }}>
            <PlayStudentRow game={game} thinking={gameThinking} />
          </div>
        </>
      );
      stageChrome = PLAY_COACH_MIN_PX + PLAY_STUDENT_ROW_PX;
    }

    return (
      <div data-testid="coach-page" data-mode={mode}>
        <CoachShell
          bar={
            <ContextBar
              title={sessionTitle || t('title')}
              subtitle={subtitle}
              sessionsOpen={sessionsOpen}
              onOpenSessions={() => setSessionsOpen(true)}
              trailing={
                openedGames.length > 0 && (
                  <ViewerTabsSheet
                    compact
                    tabs={viewerTabs}
                    activeId={activeGameId}
                    onSelect={selectTab}
                    onClose={handleCloseGame}
                    open={tabsOpen}
                    onOpenChange={setTabsOpen}
                  />
                )
              }
              menu={{
                onPlay: gameLive ? null : () => setGameDialogOpen(true),
                onImport: () => chatRef.current?.openAttach(),
                onFlip: () => board.applyBoardAction({ type: 'flip_board' }),
                onBoardTabs: openedGames.length > 0 ? () => setTabsOpen(true) : null,
                onNewSession: handleNewSession,
              }}
            />
          }
          above={above}
          board={stageBoard}
          below={belowBoard}
          stageChrome={stageChrome}
          peekPx={peekPx}
          detent={sheetDetent}
          onSheet={dispatchSheet}
          sheet={coachChat}
          keyboard={keyboard}
        />
        {sessionsOpen && (
          <CoachSessions
            variant="sheet"
            currentSessionId={sessionId}
            onSelect={handleSelectSession}
            onNew={handleNewSession}
            onClose={() => setSessionsOpen(false)}
          />
        )}
        {playSetup}
      </div>
    );
  }

  return (
    <div className="h-screen supports-[height:100dvh]:h-[100dvh] flex flex-col" data-testid="coach-page" data-mode={mode}>
      {/* Header */}
      <header className="flex items-center justify-between gap-2 px-2 sm:px-4 py-1.5 sm:py-2 border-b border-white/10">
        <div className="flex items-center gap-2 sm:gap-3 shrink-0">
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
          <h1 className="text-base sm:text-lg font-semibold text-white whitespace-nowrap">{t('title')}</h1>
          {board.puzzleMode && (
            <span className="text-xs px-2 py-0.5 bg-yellow-500/20 text-yellow-400 rounded">
              {t('puzzleMode')}
            </span>
          )}
        </div>
        <div className="relative flex items-center gap-2 sm:gap-3 min-w-0">
          <button
            onClick={() => setGameDialogOpen(true)}
            disabled={gameLive}
            className="text-xs sm:text-sm whitespace-nowrap text-gray-400 hover:text-white transition-colors disabled:opacity-40"
            data-testid="play-coach"
          >
            {t('playWithCoach')}
          </button>
          <button
            onClick={() => setSessionsOpen((v) => !v)}
            className="text-xs sm:text-sm whitespace-nowrap text-gray-400 hover:text-white transition-colors"
            aria-expanded={sessionsOpen}
          >
            {t('sessions')}
          </button>
          <button
            onClick={handleNewSession}
            className="text-xs sm:text-sm whitespace-nowrap text-gray-400 hover:text-white transition-colors"
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

      {playSetup}

      {/* Main content: Board + Chat split */}
      <div className="flex-1 min-h-0 flex flex-col lg:flex-row overflow-hidden">
        {/* Board panel */}
        <div className="lg:w-[55%] flex flex-col p-2 sm:p-4 relative">
          {openedGames.length > 0 && (
            // Opened games: one stack chip; the sheet lists, switches and closes them.
            <div className="flex justify-center pb-2">
              <ViewerTabsSheet tabs={viewerTabs} activeId={activeGameId} onSelect={selectTab} onClose={handleCloseGame} />
            </div>
          )}
          <div ref={measureBoardArea} className="flex-1 min-h-0 flex items-center justify-center">
            {activeGameId && activeGame ? (
              <div className={`flex gap-2 ${gameLayout.beside ? 'flex-row items-start' : 'flex-col items-center'}`}>
                <CoachBoard
                  fen={
                    (gameMoveIndices[activeGameId] ?? -1) === -1
                      ? activeGame.startingFen
                      : activeGame.fens[gameMoveIndices[activeGameId]]
                  }
                  arrows={viewerAnnotations.arrows as Array<{ from: Key; to: Key; brush: string }>}
                  highlights={viewerAnnotations.highlights as Key[]}
                  orientation={board.orientation}
                  onMove={() => {}}
                  onReset={() => jumpTab(activeGameId, () => -1)}
                  onFirst={() => jumpTab(activeGameId, () => -1)}
                  onPrev={() => jumpTab(activeGameId, (i) => Math.max(-1, i - 1))}
                  onNext={() => jumpTab(activeGameId, (i) => Math.min(activeGame.moves.length - 1, i + 1))}
                  onLast={() => jumpTab(activeGameId, () => activeGame.moves.length - 1)}
                  onFlip={() => board.applyBoardAction({ type: 'flip_board' })}
                  boardSize={gameLayout.size}
                />
                <div style={{ width: gameLayout.panelWidth }} data-testid="game-viewer-side">
                  <ViewerMoveList
                    moves={activeGame.moves}
                    currentIndex={gameMoveIndices[activeGameId] ?? -1}
                    onJump={(index) => jumpTab(activeGameId, () => index)}
                    layout={gameLayout.beside ? 'list' : 'strip'}
                    maxHeight={gameLayout.size + 38}
                  />
                </div>
              </div>
            ) : game ? (
              <div className="flex flex-col items-center gap-1">
                <PlayStrip comment={coachLine} width={responsiveBoardSize} {...playActions!}>
                  {studyBoard}
                </PlayStrip>
                {gameErrorLine}
              </div>
            ) : puzzleFlow ? (
              <div className="flex flex-col items-center gap-2" style={{ width: responsiveBoardSize }}>
                {studyBoard}
                {puzzleFlow}
              </div>
            ) : (
              studyBoard
            )}
          </div>
        </div>

        {/* Chat panel */}
        <div className="flex-1 lg:flex-none lg:w-[45%] border-t lg:border-t-0 lg:border-l border-white/10 flex flex-col min-h-0">
          {coachChat}
        </div>
      </div>
    </div>
  );
}
