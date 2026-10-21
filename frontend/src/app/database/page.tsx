'use client';

import { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { useSearchParams } from 'next/navigation';
import { useAuth } from '@clerk/nextjs';
import { useTranslations } from 'next-intl';
import { encodeGameSlug, decodeGameSlug, type GameSource } from '@/lib/gameSlug';
import { Box, Typography, Snackbar, Alert, Chip, Switch } from '@mui/material';
import { useBackendHealth } from '@/hooks/useBackendHealth';
import { apiFetch } from '@/lib/api';
import dynamic from 'next/dynamic';
import { Chess } from 'chess.js';
// Import chessground CSS at page level to ensure it's included in the page's CSS bundle
// (dynamic imports with ssr:false may not reliably load CSS chunks in turbopack)
import 'chessground/assets/chessground.base.css';
import 'chessground/assets/chessground.brown.css';
import '@/styles/chessground-theme.css';
import { useMasterGames } from '@/hooks/useMasterGames';
import type { GameSearchResult, MoveCandidate } from '@/hooks/useMasterGames';
import type { OpeningNode } from '@/types/openingNode';
import { findEcoOpening } from '@/lib/openingdatabase/ecoDatabase';
import type { ExplorerTab } from '@/components/openings/ExplorerTabs';
import type { MoveTreeSource } from '@/components/openings/MoveTree';
import type { MasterGamesFilterState } from '@/components/openings/MasterGamesFilter';
import { useLichessExplorer } from '@/hooks/useLichessExplorer';
import { useReplayStockfish } from '@/hooks/useReplayStockfish'
import { engineVariantLabel } from '@/lib/engine/engineVariantLabel';
import { useEngineDisplaySettings } from '@/hooks/useEngineDisplaySettings';
import EngineSettingsMenu from '@/components/engine/EngineSettingsMenu';
import { StockfishErrorBoundary } from '@/components/chess/StockfishErrorBoundary';
import StartReviewButton from '@/components/review/StartReviewButton';
import { useMoveVoiceNotes } from '@/hooks/useMoveVoiceNotes';
import { nodePathMap } from '@/lib/voiceNotes';
import { debutBoardSize, evalBarGutter, EVAL_BAR_WIDTH_PX } from '@/lib/debutBoardSize';

// Dynamic imports to avoid SSR issues
const DebutBoard = dynamic(() => import('@/components/openings/DebutBoard'), {
  ssr: false,
  loading: () => <div className="animate-pulse h-80 bg-stone-200 rounded-xl" />
});
const MasterGamesPanel = dynamic(() => import('@/components/openings/MasterGamesPanel'), {
  ssr: false,
  loading: () => <div className="animate-pulse h-60 bg-stone-200 rounded-xl" />
});
const MoveTree = dynamic(() => import('@/components/openings/MoveTree'), {
  ssr: false,
  loading: () => <div className="animate-pulse h-32 bg-stone-200 rounded-xl" />
});
const PositionSummary = dynamic(() => import('@/components/openings/PositionSummary'), {
  ssr: false,
  loading: () => null
});
const ReplayEngineLines = dynamic(() => import('@/components/opponent/ReplayEngineLines'), {
  ssr: false,
  loading: () => null
});
const ReplayEvalBar = dynamic(() => import('@/components/opponent/ReplayEvalBar'), {
  ssr: false,
  loading: () => null
});
const MyGamesPanel = dynamic(() => import('@/components/openings/MyGamesPanel'), {
  ssr: false,
  loading: () => <div className="animate-pulse h-60 bg-stone-200 rounded-xl" />
});
const MyGamesMoveList = dynamic(() => import('@/components/openings/MyGamesMoveList'), {
  ssr: false,
  loading: () => <div className="animate-pulse h-20 bg-stone-200 rounded-xl" />
});
const DatabasePillRow = dynamic(() => import('@/components/openings/DatabasePillRow'), {
  ssr: false,
  loading: () => null
});

import type { OpenedGame } from '@/components/openings/GameViewerPanel';
import { parseGamePgn, isVariationGame } from '@/components/openings/GameViewerPanel';
import { createTreeSaver, saveVariationTitle, treeAutoSaveEntry, type SaveGameTreeDeps } from '@/components/openings/saveGameTree';
import { useAutoSave } from '@/components/openings/useAutoSave';
const GameViewerPanel = dynamic(() => import('@/components/openings/GameViewerPanel'), {
  ssr: false,
  loading: () => null
});
const EditGameModal = dynamic(() => import('@/components/openings/EditGameModal'), {
  ssr: false,
  loading: () => null
});
import { useUserGames, type UserGame } from '@/hooks/useUserGames';
import { useGameMoveTree, findNodeById as findGameTreeNode, findParentOf as findGameTreeParent } from '@/hooks/useGameMoveTree';
import type { MoveContextMenuActions, VoiceNotePlayback } from '@/components/openings/MoveNotation';
import type { SquareBadge } from '@/components/openings/DebutBoard';
import { NAGS, moveQualityNag, nagBadgeColor } from '@/lib/nags';
import { Close } from '@mui/icons-material';

const STARTING_FEN = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1';

// Incoming share-link params (?g= / ?game=&source= / ?gu=) must survive two
// hazards before the game actually opens: the URL-sync effect strips them from
// the address bar while no game tab is open yet, and the page can mount twice
// on arrival with the first instance's state updates silently discarded. Stash
// them at module level and clear only once the game has opened (or the link is
// known to be bad), so a remount can still consume them.
const pendingShareParams: {
  g: string | null;
  game: string | null;
  source: string | null;
  gu: string | null;
  gc: string | null;
  sdb: string | null;
} = { g: null, game: null, source: null, gu: null, gc: null, sdb: null };

function clearPendingGameParams() {
  pendingShareParams.g = null;
  pendingShareParams.game = null;
  pendingShareParams.source = null;
}

// Extract PGN tag pairs (e.g. [White "Kasparov"]) so a deep-linked game tab can
// show real player names/result instead of placeholders.
function parsePgnHeaders(pgn: string): Record<string, string> {
  const tags: Record<string, string> = {};
  const re = /\[(\w+)\s+"([^"]*)"\]/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(pgn)) !== null) tags[m[1]] = m[2];
  return tags;
}

// Suspended in-flight requests (e.g. iOS backgrounding the service worker) never
// settle, leaving loading state stuck forever — force-reject so the UI recovers.
const FETCH_TIMEOUT_MS = 12000;
function withTimeout<T>(promise: Promise<T>, ms = FETCH_TIMEOUT_MS): Promise<T> {
  return Promise.race([
    promise,
    new Promise<T>((_, reject) => setTimeout(() => reject(new Error('fetch timeout')), ms)),
  ]);
}

export default function DebutPage() {
  const t = useTranslations('debut');
  const backendHealthy = useBackendHealth();
  const { isLoaded: authLoaded, isSignedIn, getToken } = useAuth();

  // mounted guard removed — dynamic imports with ssr:false handle this

  // ─── Master tab board: in-memory move history (nothing is saved) ───
  const [masterFens, setMasterFens] = useState<string[]>([STARTING_FEN]);
  const [masterIndex, setMasterIndex] = useState(0);
  const boardFen = masterFens[masterIndex];
  const [boardOrientation, setBoardOrientation] = useState<'white' | 'black'>('white');

  // ─── Shared collection (read-only recipient view) state ───
  // Set from ?gc=<token>; when present the My Games tab renders MyGamesPanel in
  // read-only shared mode against the owner's collection.
  const [sharedCollectionToken, setSharedCollectionToken] = useState<string | null>(null);

  // ─── Shared *database* (per-db ?sdb token) read-only view + copy ───
  const [sharedDatabaseToken, setSharedDatabaseToken] = useState<string | null>(null);
  // Bumped to force the database pill row to re-fetch (after copy-to-workspace).
  const [pillReloadKey, setPillReloadKey] = useState(0);

  // ─── My Games tab board interaction state ───
  const [myGamesMoveHistory, setMyGamesMoveHistory] = useState<string[]>([STARTING_FEN]);
  const [myGamesMoveIndex, setMyGamesMoveIndex] = useState(0);
  const [myGamesSanMoves, setMyGamesSanMoves] = useState<string[]>([]);
  const [myGamesComments, setMyGamesComments] = useState<Record<number, string>>({});

  // ─── Auto-fetched master games ───
  const [masterGames, setMasterGames] = useState<GameSearchResult[]>([]);
  const [masterGamesTotal, setMasterGamesTotal] = useState(0);
  const [masterGamesLoading, setMasterGamesLoading] = useState(false);

  // ─── Master games filters ───
  const [masterGamesFilters, setMasterGamesFilters] = useState<MasterGamesFilterState>({
    playerName: '',
    opponentName: '',
    playerColor: '',
    result: '',
    sortBy: 'date_desc',
    whiteEloMin: 0,
    whiteEloMax: 3500,
    blackEloMin: 0,
    blackEloMax: 3500,
    dateFrom: '',
    dateTo: '',
    ecoCode: '',
    eventName: ''
  });

  // ─── Move tree (candidates) ───
  const [candidateMoves, setCandidateMoves] = useState<MoveCandidate[]>([]);
  const [candidatesTotalGames, setCandidatesTotalGames] = useState(0);
  const [candidatesLoading, setCandidatesLoading] = useState(false);

  // ─── Master DB global stats (updated weekly by TWIC Phase 1) ───
  const [masterDbGameCount, setMasterDbGameCount] = useState<number | null>(null);
  useEffect(() => {
    let cancelled = false;
    const apiBase = process.env.NEXT_PUBLIC_API_URL || '';
    apiFetch<{ game_count: number }>(`${apiBase}/api/opponent/status`)
      .then(data => { if (!cancelled) setMasterDbGameCount(data.game_count); })
      .catch(() => { /* silent: strip just hides */ });
    return () => { cancelled = true; };
  }, []);


  // ─── Game viewer tabs ───
  const [openedGames, setOpenedGames] = useState<OpenedGame[]>([]);
  const [activeTab, setActiveTab] = useState<string>('debut');
  // Active database for the pill row: null = Master (TWIC) view. Selecting a
  // user database scopes the My Games list to that database_id.
  const [selectedDatabaseId, setSelectedDatabaseId] = useState<string | null>(null);
  const [gameMoveIndices, setGameMoveIndices] = useState<Record<string, number>>({});
  // Track the last non-game tab so closing a game returns to the right place
  const lastHomeTabRef = useRef<string>('debut');
  useEffect(() => {
    if (activeTab === 'debut' || activeTab === 'my-games') {
      lastHomeTabRef.current = activeTab;
    }
  }, [activeTab]);

  // ─── Explorer tabs state ───
  const [explorerTab, setExplorerTab] = useState<ExplorerTab>('twic');
  const [lichessDatabase, setLichessDatabase] = useState<'masters' | 'lichess'>('lichess');
  const [moveTreeSource, setMoveTreeSource] = useState<MoveTreeSource>('twic');

  // ─── Stockfish analysis toggle ───
  // Never auto-enable from localStorage — WASM SIGILL crashes kill the tab
  // and localStorage persistence causes an unrecoverable crash loop on reload.
  // User must explicitly click the toggle each session.
  const [stockfishEnabled, setStockfishEnabled] = useState(false);
  const stockfishErrorMsgRef = useRef<string | null>(null);
  const handleStockfishError = useCallback((msg: string) => {
    stockfishErrorMsgRef.current = msg;
  }, []);
  const { depth: engineDepth, lines: engineLines } = useEngineDisplaySettings();
  const { evaluation, isAnalyzing, isReady, depth, engineError, engineName, analyze, stopAnalysis } = useReplayStockfish({ enabled: stockfishEnabled, depth: engineDepth, multiPv: engineLines, onError: handleStockfishError });

  const toggleStockfish = useCallback(() => {
    const scrollY = window.scrollY;
    if (document.activeElement instanceof HTMLElement) {
      document.activeElement.blur();
    }
    setStockfishEnabled(prev => !prev);
    // Restore scroll position after React re-render adds/removes Stockfish content
    requestAnimationFrame(() => {
      window.scrollTo(0, scrollY);
    });
  }, []);

  // ─── Board size (mirrors DebutBoard logic for eval bar height) ───
  const [windowWidth, setWindowWidth] = useState(1024);
  useEffect(() => {
    setWindowWidth(window.innerWidth);
    const handleResize = () => setWindowWidth(window.innerWidth);
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);
  // The eval bar sits left of the board; on phones the board gives up its width.
  // Eval bar room depends on viewport only, so the Stockfish toggle never shifts the board.
  const evalBarReserve = evalBarGutter(windowWidth);
  const boardSize = useMemo(() => debutBoardSize(windowWidth, evalBarReserve), [windowWidth, evalBarReserve]);

  // ─── Snackbar ───
  const [snackbar, setSnackbar] = useState<{ open: boolean; msg: string; severity: 'success' | 'error' }>({ open: false, msg: '', severity: 'success' });

  // Show snackbar when Stockfish error occurs
  useEffect(() => {
    if (engineError) {
      setSnackbar({ open: true, msg: `Stockfish: ${engineError}`, severity: 'error' });
    }
  }, [engineError]);

  // ─── My Games (save bookmark + edit) ───
  const { createGame: createUserGame, updateGame: updateUserGame, toggleFavorite: toggleUserFavorite, deleteGame: deleteUserGame } = useUserGames();
  const [savedGameIds, setSavedGameIds] = useState<Set<string>>(new Set());
  const [favoriteGameIds, setFavoriteGameIds] = useState<Set<string>>(new Set());
  const [editModalOpen, setEditModalOpen] = useState(false);
  const [editingGame, setEditingGame] = useState<UserGame | null>(null);
  // Bumped after a board-side save so My Games refetches its Analysis list.
  const [myGamesRefreshKey, setMyGamesRefreshKey] = useState(0);

  // ─── Game move tree editing (for user games) ───
  const gameMoveTree = useGameMoveTree();
  const [editTreeSelectedNodeId, setEditTreeSelectedNodeId] = useState<string | null>(null);
  const [editTreeGameId, setEditTreeGameId] = useState<string | null>(null);

  const handleSaveToMyGames = useCallback(async (game: OpenedGame): Promise<boolean> => {
    try {
      const result = await createUserGame(game.pgn, {
        white: game.white,
        black: game.black,
        white_elo: game.whiteElo ?? null,
        black_elo: game.blackElo ?? null,
        result: game.result,
        date: game.date ?? null,
        event: game.event ?? null,
        eco: game.eco ?? null,
        source: typeof game.source === 'string' ? game.source : 'database',
      });
      if (result) {
        setSavedGameIds(prev => new Set(prev).add(game.id));
        setSnackbar({ open: true, msg: t('gameSavedToMyGames'), severity: 'success' });
        return true;
      }
      setSnackbar({ open: true, msg: t('gameSaveFailed'), severity: 'error' });
      return false;
    } catch {
      setSnackbar({ open: true, msg: t('gameSaveFailed'), severity: 'error' });
      return false;
    }
  }, [createUserGame, t]);

  const handleEditGameFromViewer = useCallback((game: OpenedGame) => {
    // Build a UserGame-like object from the OpenedGame so the modal can pre-populate
    const userGame: UserGame = {
      id: game.id,
      user_id: '',
      title: null,
      white: game.white,
      black: game.black,
      white_elo: game.whiteElo ?? null,
      black_elo: game.blackElo ?? null,
      result: game.result,
      date: game.date ?? null,
      event: game.event ?? null,
      eco: game.eco ?? null,
      opening_name: null,
      pgn: game.pgn,
      notes: null,
      tags: [],
      is_favorite: false,
      source: typeof game.source === 'string' ? game.source : 'user',
      created_at: '',
      updated_at: '',
    };
    setEditingGame(userGame);
    setEditModalOpen(true);
  }, []);

  const handleEditGameSave = useCallback(async (
    id: string,
    updates: Partial<Omit<UserGame, 'id' | 'user_id' | 'created_at'>>
  ): Promise<UserGame | null> => {
    const result = await updateUserGame(id, updates);
    if (result) {
      // Update the opened game tab metadata to reflect the edit
      setOpenedGames(prev => prev.map(g => {
        if (g.id !== id) return g;
        return {
          ...g,
          white: result.white ?? g.white,
          black: result.black ?? g.black,
          whiteElo: result.white_elo ?? g.whiteElo,
          blackElo: result.black_elo ?? g.blackElo,
          result: result.result ?? g.result,
          date: result.date ?? g.date,
          event: result.event ?? g.event,
          eco: result.eco ?? g.eco,
        };
      }));
      setSnackbar({ open: true, msg: t('myGames.editModal.updateSuccess'), severity: 'success' });
    }
    return result;
  }, [updateUserGame, t]);

  // ─── Viewer actions: toggle favorite / delete game ───
  const handleViewerToggleFavorite = useCallback(async () => {
    if (!activeTab) return;
    const success = await toggleUserFavorite(activeTab);
    if (success) {
      setFavoriteGameIds(prev => {
        const next = new Set(prev);
        if (next.has(activeTab)) { next.delete(activeTab); } else { next.add(activeTab); }
        return next;
      });
    }
  }, [activeTab, toggleUserFavorite]);

  // Rename a variation: a draft's title lives in tab state (a non-empty one
  // triggers its auto-create); saved ones update immediately and revert on failure.
  const handleVariationTitleChange = useCallback(async (game: OpenedGame, title: string | null) => {
    const setTitle = (value: string | undefined) =>
      setOpenedGames(prev => prev.map(g => (g.id === game.id ? { ...g, title: value } : g)));
    setTitle(title ?? undefined);
    const ok = await saveVariationTitle(game, title, updateUserGame);
    if (!ok) {
      setTitle(game.title);
      setSnackbar({ open: true, msg: t('myGames.titleSaveError'), severity: 'error' });
      return;
    }
    setMyGamesRefreshKey(k => k + 1);
  }, [updateUserGame, t]);

  // ─── Game move tree: init when opening a user game ───
  const activeGameForTree = openedGames.find(g => g.id === activeTab);
  const isActiveGameEditable = activeGameForTree?.source === 'user' && !activeGameForTree.readOnly;
  // Shared-database games are browsed as a read-only tree (variations + voice notes).
  const isActiveGameTree = isActiveGameEditable || !!activeGameForTree?.sharedDbToken;

  // Initialize tree when switching to a user game tab
  useEffect(() => {
    if (isActiveGameTree && activeGameForTree && editTreeGameId !== activeGameForTree.id) {
      gameMoveTree.initFromPgn(activeGameForTree.pgn);
      setEditTreeGameId(activeGameForTree.id);
      setEditTreeSelectedNodeId(null);
    }
  }, [isActiveGameTree, activeGameForTree?.id, activeGameForTree?.pgn, editTreeGameId, gameMoveTree]);

  const handleEditNodeSelect = useCallback((node: OpeningNode) => {
    setEditTreeSelectedNodeId(node.id);
  }, []);

  const handleGameBoardMove = useCallback((
    _from: string, _to: string, _piece: string, _newFen: string, moveSan: string, _moveUci: string
  ) => {
    if (!gameMoveTree.tree) return;
    // No selection means the board shows the root, so the move belongs there.
    // addMove re-validates from the parent and returns an existing child if present.
    const result = gameMoveTree.addMove(editTreeSelectedNodeId ?? gameMoveTree.tree.id, moveSan);
    if (result) setEditTreeSelectedNodeId(result.id);
  }, [gameMoveTree, editTreeSelectedNodeId]);

  // ─── Auto-save of the edited tree (own games + variation drafts) ───
  // Only once the tree belongs to the active tab; right after a tab switch it
  // still holds the previous game until the init effect above re-parses it.
  const editTreeIsLive = isActiveGameEditable && !!gameMoveTree.tree && editTreeGameId === activeGameForTree?.id;
  const getEditTreePgn = gameMoveTree.getPgn;
  const editTreePgn = useMemo(() => (editTreeIsLive ? getEditTreePgn() : ''), [editTreeIsLive, getEditTreePgn]);
  const autoSaveEntry = editTreeIsLive
    ? treeAutoSaveEntry(activeGameForTree, editTreePgn, {
      hasMoves: !!gameMoveTree.tree?.children?.length,
      isDirty: gameMoveTree.isDirty,
    })
    : null;

  const saveDepsRef = useRef<SaveGameTreeDeps | null>(null);
  useEffect(() => {
    saveDepsRef.current = { databaseId: selectedDatabaseId, createGame: createUserGame, updateGame: updateUserGame };
  });
  const [saveTreeSnapshot] = useState(() => createTreeSaver(
    () => saveDepsRef.current!,
    ({ oldId, newId, pgn }) => {
      setMyGamesRefreshKey(k => k + 1);
      // A created draft takes over the real game id so later saves update it in place.
      const parsed = parseGamePgn(pgn);
      setOpenedGames(prev => prev.map(g => (
        g.id === oldId ? { ...g, id: newId, isDraft: undefined, pgn, moves: parsed.moves, fens: parsed.fens } : g
      )));
      if (newId === oldId) return;
      setGameMoveIndices(prev => {
        const { [oldId]: idx, ...rest } = prev;
        return { ...rest, [newId]: idx ?? -1 };
      });
      // Keep the live tree (and selection) instead of re-parsing on the id change
      setEditTreeGameId(cur => (cur === oldId ? newId : cur));
      setActiveTab(cur => (cur === oldId ? newId : cur));
    },
  ));

  const { status: saveStatus, flush: flushAutoSave, discard: discardAutoSave } = useAutoSave({
    scope: activeTab,
    entry: autoSaveEntry,
    save: saveTreeSnapshot,
    onClean: gameMoveTree.markClean,
    // A draft is created on its first move / title; later edits are debounced.
    delayMs: activeGameForTree?.isDraft ? 0 : 1500,
    leaveWarning: t('myGames.autoSave.unsavedLeaveWarning'),
  });
  const editTreeHasUnsaved = autoSaveEntry !== null || saveStatus === 'error';

  const handleEditTreeSaveNow = useCallback(async () => {
    const wasDraft = !!activeGameForTree?.isDraft;
    const ok = await flushAutoSave();
    setSnackbar(ok
      ? { open: true, msg: wasDraft ? t('myGames.variationSaved') : t('myGames.moveEdit.savedSuccessfully'), severity: 'success' }
      : { open: true, msg: t('myGames.editModal.updateFailed'), severity: 'error' });
  }, [activeGameForTree?.isDraft, flushAutoSave, t]);

  const handleRetrySave = useCallback(() => { flushAutoSave(); }, [flushAutoSave]);

  // Review the moves as shown: an edited own game reviews its live tree (the PGN
  // auto-save writes), so a just-made edit counts before the debounced save lands.
  const reviewPgn = editTreeIsLive
    ? (gameMoveTree.tree?.children?.length ? editTreePgn : '')
    : (activeGameForTree?.moves.length ? activeGameForTree.pgn : '');

  const handleViewerDeleteGame = useCallback(async () => {
    if (!activeTab) return;
    // A pending save of the deleted game could only fail from now on.
    discardAutoSave();
    const success = await deleteUserGame(activeTab);
    if (success) {
      // Close the viewer tab
      setOpenedGames(prev => prev.filter(g => g.id !== activeTab));
      setGameMoveIndices(prev => {
        const next = { ...prev };
        delete next[activeTab];
        return next;
      });
      setActiveTab(lastHomeTabRef.current);
      setSnackbar({ open: true, msg: 'Game deleted', severity: 'success' });
    }
  }, [activeTab, deleteUserGame, discardAutoSave]);

  // ─── Voice notes on moves (saved own games; read-only for shared databases) ───
  const voiceGameId = activeGameForTree && !activeGameForTree.isDraft && isActiveGameTree ? activeGameForTree.id : null;
  const voiceNotes = useMoveVoiceNotes({
    gameId: voiceGameId,
    shareToken: activeGameForTree?.sharedDbToken,
    onError: (kind) => setSnackbar({ open: true, msg: t(`myGames.voiceNote.errors.${kind}`), severity: 'error' }),
  });
  const movePath = useCallback((nodeId: string) => (
    gameMoveTree.tree ? nodePathMap(gameMoveTree.tree).get(nodeId) ?? null : null
  ), [gameMoveTree.tree]);
  const voicePlayback: VoiceNotePlayback | undefined = voiceGameId ? {
    paths: voiceNotes.paths,
    playingPath: voiceNotes.playingPath,
    onToggle: voiceNotes.toggle,
    playLabel: t('myGames.voiceNote.play'),
    pauseLabel: t('myGames.voiceNote.pause'),
  } : undefined;
  const canRecordVoice = isActiveGameEditable && !!voiceGameId;

  const editContextMenuActions: MoveContextMenuActions | undefined = isActiveGameEditable ? {
    onDeleteMove: (node) => {
      // Its voice notes (and those of every later move in the line) go with it.
      const path = movePath(node.id);
      // Select the previous move (the tree root before the first move).
      const parentId = gameMoveTree.deleteFromHere(node.id);
      if (parentId) setEditTreeSelectedNodeId(parentId);
      if (path) voiceNotes.removeFrom(path);
    },
    onDeleteVariation: (node) => {
      const path = movePath(node.id);
      if (path) voiceNotes.removeFrom(path);
      gameMoveTree.deleteVariation(node.id);
      if (gameMoveTree.tree) {
        const findParent = (root: OpeningNode, targetId: string): OpeningNode | null => {
          for (const child of root.children || []) {
            if (child.id === targetId) return root;
            const found = findParent(child, targetId);
            if (found) return found;
          }
          return null;
        };
        const parent = findParent(gameMoveTree.tree, node.id);
        setEditTreeSelectedNodeId(parent?.id || gameMoveTree.tree.id);
      }
    },
    onPromoteVariation: (node) => {
      gameMoveTree.promoteVariation(node.id);
    },
    onMakeMainLine: (node) => {
      gameMoveTree.makeMainLine(node.id);
    },
    onCommentChange: (node, text) => {
      gameMoveTree.setComment(node.id, text);
    },
    onNagToggle: (node, code) => {
      gameMoveTree.toggleNag(node.id, code);
    },
    onVoiceNoteSave: canRecordVoice ? async (node, recording) => {
      const path = movePath(node.id);
      const ok = !!path && await voiceNotes.save(path, recording);
      if (ok) setSnackbar({ open: true, msg: t('myGames.voiceNote.saved'), severity: 'success' });
      return ok;
    } : undefined,
    onVoiceNoteDelete: canRecordVoice ? (node) => {
      const path = movePath(node.id);
      if (path) voiceNotes.remove(path);
    } : undefined,
    labels: {
      deleteMove: t('myGames.moveEdit.deleteMove'),
      deleteVariation: t('myGames.moveEdit.deleteVariation'),
      promoteVariation: t('myGames.moveEdit.promoteVariation'),
      makeMainLine: t('myGames.moveEdit.makeMainLine'),
      addComment: t('myGames.moveEdit.addComment'),
      editComment: t('myGames.moveEdit.editComment'),
      commentPlaceholder: t('myGames.moveEdit.commentPlaceholder'),
      comment: t('myGames.moveEdit.comment'),
      symbols: t('myGames.moveEdit.symbols'),
      more: t('myGames.moveEdit.more'),
      moreActions: t('myGames.moveEdit.moreActions'),
      saveComment: t('myGames.moveEdit.saveComment'),
      cancel: t('myGames.moveEdit.cancel'),
      deleteComment: t('myGames.moveEdit.deleteComment'),
      voiceNote: t('myGames.voiceNote.record'),
      rerecordVoiceNote: t('myGames.voiceNote.rerecord'),
      deleteVoiceNote: t('myGames.voiceNote.delete'),
      voice: t('myGames.voiceNote.short'),
      recorder: {
        record: t('myGames.voiceNote.recorder.record'),
        stop: t('myGames.voiceNote.recorder.stop'),
        save: t('myGames.voiceNote.recorder.save'),
        rerecord: t('myGames.voiceNote.recorder.rerecord'),
        cancel: t('myGames.voiceNote.recorder.cancel'),
        saving: t('myGames.voiceNote.recorder.saving'),
        hint: t('myGames.voiceNote.recorder.hint'),
        micDenied: t('myGames.voiceNote.recorder.micDenied'),
        micUnavailable: t('myGames.voiceNote.recorder.micUnavailable'),
        saveFailed: t('myGames.voiceNote.recorder.saveFailed'),
      },
      moveSymbols: t('nags.moveSymbols'),
      moreSymbols: t('nags.moreSymbols'),
      fewerSymbols: t('nags.fewerSymbols'),
      nagNames: Object.fromEntries(NAGS.map(n => [n.i18nKey, t(`nags.${n.i18nKey}`)])),
    },
  } : undefined;

  // Get the FEN for the selected tree node (when viewing an editable game).
  // With nothing selected the board must show the tree root, matching where moves attach.
  const editTreeFen = useMemo(() => {
    if (!isActiveGameTree || !gameMoveTree.tree) return null;
    if (!editTreeSelectedNodeId) return gameMoveTree.tree.fen;
    const node = findGameTreeNode(gameMoveTree.tree, editTreeSelectedNodeId);
    return node?.fen || gameMoveTree.tree.fen;
  }, [isActiveGameTree, gameMoveTree.tree, editTreeSelectedNodeId]);

  // Move-quality symbol of the selected move, pinned to its destination square.
  const editTreeBadge = useMemo((): SquareBadge | null => {
    if (!isActiveGameTree || !gameMoveTree.tree || !editTreeSelectedNodeId) return null;
    const node = findGameTreeNode(gameMoveTree.tree, editTreeSelectedNodeId);
    const quality = moveQualityNag(node?.nags);
    if (!quality || !node?.move_uci) return null;
    return { square: node.move_uci.slice(2, 4), symbol: quality.symbol, color: nagBadgeColor(quality) };
  }, [isActiveGameTree, gameMoveTree.tree, editTreeSelectedNodeId]);

  // ─── Tree navigation callbacks (for DebutBoard arrows + keyboard in tree mode) ───
  const handleEditTreePrev = useCallback(() => {
    if (!gameMoveTree.tree || !editTreeSelectedNodeId) return;
    const parent = findGameTreeParent(gameMoveTree.tree, editTreeSelectedNodeId);
    if (parent) setEditTreeSelectedNodeId(parent.id);
  }, [gameMoveTree.tree, editTreeSelectedNodeId]);

  const handleEditTreeNext = useCallback(() => {
    if (!gameMoveTree.tree) return;
    const node = findGameTreeNode(gameMoveTree.tree, editTreeSelectedNodeId ?? gameMoveTree.tree.id);
    if (node?.children?.length) setEditTreeSelectedNodeId(node.children[0].id);
  }, [gameMoveTree.tree, editTreeSelectedNodeId]);

  const handleEditTreeGoToStart = useCallback(() => {
    if (!gameMoveTree.tree) return;
    setEditTreeSelectedNodeId(gameMoveTree.tree.id);
  }, [gameMoveTree.tree]);

  const handleEditTreeGoToEnd = useCallback(() => {
    if (!gameMoveTree.tree) return;
    let node = findGameTreeNode(gameMoveTree.tree, editTreeSelectedNodeId ?? gameMoveTree.tree.id);
    if (!node) return;
    while (node.children?.length) node = node.children[0];
    setEditTreeSelectedNodeId(node.id);
  }, [gameMoveTree.tree, editTreeSelectedNodeId]);

  // ─── My Games tab board interaction handlers ───
  const myGamesFen = myGamesMoveHistory[myGamesMoveIndex];

  const handleMyGamesBoardMove = useCallback((
    _from: string, _to: string, _piece: string, newFen: string, moveSan: string, _moveUci: string
  ) => {
    // DebutBoard already validated the move via Chess.js and provides the new FEN
    // Truncate history if branching from a non-end position
    setMyGamesMoveHistory(prev => [...prev.slice(0, myGamesMoveIndex + 1), newFen]);
    setMyGamesSanMoves(prev => {
      const truncated = prev.slice(0, myGamesMoveIndex);
      return [...truncated, moveSan];
    });
    // Remove comments for any truncated moves
    setMyGamesComments(prev => {
      const next = { ...prev };
      // Remove comments for moves beyond the new length
      for (const key of Object.keys(next)) {
        if (Number(key) > myGamesMoveIndex) {
          delete next[Number(key)];
        }
      }
      return next;
    });
    setMyGamesMoveIndex(prev => prev + 1);
  }, [myGamesMoveIndex]);

  const handleMyGamesReset = useCallback(() => {
    setMyGamesMoveHistory([STARTING_FEN]);
    setMyGamesMoveIndex(0);
    setMyGamesSanMoves([]);
    setMyGamesComments({});
  }, []);

  // Delete the move at a 1-based index plus everything after it, landing on the
  // previous move.
  const handleMyGamesDeleteMove = useCallback((moveIndex: number) => {
    setMyGamesMoveHistory(prev => prev.slice(0, moveIndex));
    setMyGamesSanMoves(prev => prev.slice(0, moveIndex - 1));
    setMyGamesMoveIndex(moveIndex - 1);
    setMyGamesComments(prev => Object.fromEntries(
      Object.entries(prev).filter(([key]) => Number(key) < moveIndex),
    ));
  }, []);

  const handleMyGamesPrev = useCallback(() => {
    setMyGamesMoveIndex(prev => Math.max(0, prev - 1));
  }, []);

  const handleMyGamesNext = useCallback(() => {
    setMyGamesMoveIndex(prev => Math.min(myGamesMoveHistory.length - 1, prev + 1));
  }, [myGamesMoveHistory.length]);

  const handleMyGamesGoToEnd = useCallback(() => {
    setMyGamesMoveIndex(myGamesMoveHistory.length - 1);
  }, [myGamesMoveHistory.length]);

  const handleMyGamesComment = useCallback((moveIndex: number, comment: string) => {
    setMyGamesComments(prev => {
      if (!comment.trim()) {
        const next = { ...prev };
        delete next[moveIndex];
        return next;
      }
      return { ...prev, [moveIndex]: comment };
    });
  }, []);

  const buildMyGamesPgn = useCallback(() => {
    if (myGamesSanMoves.length === 0) return '';
    let pgn = '';
    for (let i = 0; i < myGamesSanMoves.length; i++) {
      const moveNum = Math.floor(i / 2) + 1;
      const isWhite = i % 2 === 0;
      if (isWhite) {
        pgn += `${moveNum}. `;
      }
      pgn += myGamesSanMoves[i];
      // Comment uses 1-based index (moveIndex = i + 1)
      const comment = myGamesComments[i + 1];
      if (comment) {
        pgn += ` {${comment}}`;
      }
      pgn += ' ';
    }
    pgn += '*';
    return pgn.trim();
  }, [myGamesSanMoves, myGamesComments]);

  // ─── Master games API (authenticated; membership gate enforced server-side) ───
  const {
    fetchGamesByPosition, fetchPositionCount, fetchCandidateMoves, fetchGamePgn, fetchLichessPgn,
  } = useMasterGames();

  // ─── Lichess Explorer for move tree ───
  const lichessExplorerFen = moveTreeSource !== 'twic' ? boardFen : '';
  const lichessExplorerDb = moveTreeSource === 'lichess-masters' ? 'masters' : 'lichess';
  const { data: lichessExplorerData, loading: lichessExplorerLoading } = useLichessExplorer({
    fen: lichessExplorerFen,
    database: lichessExplorerDb,
    enabled: moveTreeSource !== 'twic',
  });

  // ─── URL state management ───
  useEffect(() => {
    // Read URL params on mount
    if (typeof window === 'undefined') return;
    const params = new URLSearchParams(window.location.search);
    const urlExplorer = params.get('explorer') as ExplorerTab | null;
    const urlDb = params.get('db') as 'masters' | 'lichess' | null;

    if (urlExplorer && ['twic', 'lichess', 'chesscom'].includes(urlExplorer)) {
      setExplorerTab(urlExplorer);
    }
    if (urlDb && ['masters', 'lichess'].includes(urlDb)) {
      setLichessDatabase(urlDb);
    }
  }, []);

  useEffect(() => {
    // Update URL when explorer state changes
    if (typeof window === 'undefined') return;
    const params = new URLSearchParams(window.location.search);
    params.set('explorer', explorerTab);
    if (explorerTab === 'lichess') {
      params.set('db', lichessDatabase);
    } else {
      params.delete('db');
    }
    const newUrl = `${window.location.pathname}?${params.toString()}`;
    window.history.replaceState({}, '', newUrl);
  }, [explorerTab, lichessDatabase]);

  // ─── Auto-fetch master games when the board position or filters change ───
  useEffect(() => {
    let cancelled = false;
    setMasterGamesLoading(true);

    withTimeout(fetchGamesByPosition(boardFen, 50, masterGamesFilters))
      .then((data) => {
        if (!cancelled) {
          // Deduplicate by game ID to prevent visual duplicates
          const seen = new Set<string | number>();
          const unique = data.games.filter((g: GameSearchResult) => {
            if (!g.id || seen.has(g.id)) return false;
            seen.add(g.id);
            return true;
          });
          setMasterGames(unique);

          // fetchPositionCount counts ALL games at this position, ignoring the
          // active player/result/elo filter — so it must only stand in for the
          // total when NO such filter is active. With a filter on, the total is
          // the filtered result set itself, not the unfiltered position count.
          const hasResultFilter =
            !!masterGamesFilters.playerName.trim() ||
            !!masterGamesFilters.result ||
            masterGamesFilters.whiteEloMin !== 0 || masterGamesFilters.whiteEloMax !== 3500 ||
            masterGamesFilters.blackEloMin !== 0 || masterGamesFilters.blackEloMax !== 3500;

          if (hasResultFilter) {
            setMasterGamesTotal(unique.length);
          } else {
            setMasterGamesTotal(data.total);

            // If count is approximate, fetch exact count in background.
            if (!data.count_exact && data.games.length > 0) {
              fetchPositionCount(boardFen)
                .then((count) => { if (!cancelled) setMasterGamesTotal(count); })
                .catch(() => {});
            }
          }
        }
      })
      .catch(() => {
        if (!cancelled) {
          setMasterGames([]);
          setMasterGamesTotal(0);
        }
      })
      .finally(() => {
        if (!cancelled) setMasterGamesLoading(false);
      });

    return () => { cancelled = true; };
  }, [boardFen, masterGamesFilters, fetchGamesByPosition, fetchPositionCount]);

  // ─── Auto-fetch candidate moves when the board position changes ───
  useEffect(() => {
    // Only fetch TWIC data if using TWIC source
    if (moveTreeSource !== 'twic') {
      setCandidateMoves([]);
      setCandidatesTotalGames(0);
      return;
    }

    let cancelled = false;
    setCandidatesLoading(true);

    withTimeout(fetchCandidateMoves(boardFen))
      .then((data) => {
        if (!cancelled) {
          setCandidateMoves(data.moves);
          setCandidatesTotalGames(data.total_games);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setCandidateMoves([]);
          setCandidatesTotalGames(0);
        }
      })
      .finally(() => {
        if (!cancelled) setCandidatesLoading(false);
      });

    return () => { cancelled = true; };
  }, [boardFen, fetchCandidateMoves, moveTreeSource]);

  // ─── Opening name/ECO: the deepest named position along the played line ───
  const [masterOpening, setMasterOpening] = useState<{ eco: string | null; name: string } | null>(null);
  useEffect(() => {
    let cancelled = false;
    const line = masterFens.slice(0, masterIndex + 1).reverse();
    Promise.all(line.map(findEcoOpening))
      .then(found => { if (!cancelled) setMasterOpening(found.find(Boolean) ?? null); })
      .catch(() => { if (!cancelled) setMasterOpening(null); });
    return () => { cancelled = true; };
  }, [masterFens, masterIndex]);

  // ─── Transform Lichess data to MoveCandidate format ───
  const lichessCandidateMoves = useMemo(() => {
    if (!lichessExplorerData || moveTreeSource === 'twic') return [];

    const total = lichessExplorerData.white + lichessExplorerData.draws + lichessExplorerData.black;

    return lichessExplorerData.moves.map(m => {
      const moveTotal = m.white + m.draws + m.black;
      const percentage = total > 0 ? (moveTotal / total) * 100 : 0;

      return {
        uci: m.uci,
        san: m.san,
        count: moveTotal,
        percentage,
        white_wins: m.white,
        draws: m.draws,
        black_wins: m.black,
        avg_elo: m.averageRating || null,
        avg_year: null,
        score: `${((m.white + m.draws * 0.5) / moveTotal * 100).toFixed(1)}%`,
        winrate: `${(m.white / moveTotal * 100).toFixed(1)}%`,
      } as MoveCandidate;
    });
  }, [lichessExplorerData, moveTreeSource]);

  // ─── Determine which moves to show in MoveTree ───
  const displayedMoves = moveTreeSource === 'twic' ? candidateMoves : lichessCandidateMoves;
  const displayedTotalGames = moveTreeSource === 'twic'
    ? candidatesTotalGames
    : (lichessExplorerData ? lichessExplorerData.white + lichessExplorerData.draws + lichessExplorerData.black : 0);
  const displayedLoading = moveTreeSource === 'twic' ? candidatesLoading : lichessExplorerLoading;


  // ─── Handlers ───

  // A board move branches off the shown position, dropping any forward history.
  const handleBoardMove = useCallback((
    _from: string, _to: string, _piece: string, newFen: string, _moveSan: string, _moveUci: string
  ) => {
    setMasterFens(prev => [...prev.slice(0, masterIndex + 1), newFen]);
    setMasterIndex(masterIndex + 1);
  }, [masterIndex]);

  // Candidate-move click plays the move on the board.
  // The candidates endpoint may return an empty uci, so fall back to SAN.
  const handleMoveTreeClick = useCallback((move: MoveCandidate) => {
    const chess = new Chess(boardFen);
    let result = null;
    try {
      result = move.uci && move.uci.length >= 4
        ? chess.move({
            from: move.uci.substring(0, 2),
            to: move.uci.substring(2, 4),
            promotion: move.uci.length > 4 ? move.uci[4] : undefined,
          })
        : move.san
          ? chess.move(move.san)
          : null;
    } catch {
      result = null;
    }
    if (result) {
      handleBoardMove(result.from, result.to, '', chess.fen(), result.san, result.from + result.to + (result.promotion ?? ''));
    }
  }, [boardFen, handleBoardMove]);

  // Navigation handlers
  const handleReset = useCallback(() => {
    setMasterFens([STARTING_FEN]);
    setMasterIndex(0);
  }, []);

  const handleGoToStart = useCallback(() => setMasterIndex(0), []);

  const handlePrev = useCallback(() => setMasterIndex(i => Math.max(0, i - 1)), []);

  const handleNext = useCallback(() => {
    setMasterIndex(i => Math.min(masterFens.length - 1, i + 1));
  }, [masterFens.length]);

  const handleGoToEnd = useCallback(() => setMasterIndex(masterFens.length - 1), [masterFens.length]);

  const handleFlip = useCallback(() => {
    setBoardOrientation(o => o === 'white' ? 'black' : 'white');
  }, []);

  // ─── Game viewer handlers ───
  const handleOpenGame = useCallback(async (game: any, opts?: { evictOldestIfFull?: boolean; readOnly?: boolean; sharedDbToken?: string }) => {
    const gameId = String(game.id || `${game.white_name || game.white}-${game.black_name || game.black}-${game.date}`);
    const existing = openedGames.find(g => g.id === gameId);
    if (existing) {
      setActiveTab(gameId);
      return;
    }

    // Deep-linked games (evictOldestIfFull) replace the oldest tab when full
    // instead of being refused, so a share link always opens.
    if (openedGames.length >= 10 && !opts?.evictOldestIfFull) {
      setSnackbar({ open: true, msg: t('maxTabsError'), severity: 'error' });
      return;
    }

    // If PGN not loaded yet, fetch it on demand
    let pgnText = game.pgn;
    if (!pgnText && game.id && (game.pgn_offset !== undefined || game.pgn_length !== undefined)) {
      try {
        setSnackbar({ open: true, msg: 'Loading game...', severity: 'success' });
        pgnText = await fetchGamePgn(Number(game.id));
      } catch (e: any) {
        setSnackbar({ open: true, msg: e.message || 'Failed to load PGN', severity: 'error' });
        return;
      }
    }

    // Fetch PGN for Lichess games on demand
    if (!pgnText && game.source === 'lichess' && game.id) {
      try {
        setSnackbar({ open: true, msg: 'Loading game from Lichess...', severity: 'success' });
        pgnText = await fetchLichessPgn(String(game.id));
      } catch (e: any) {
        setSnackbar({ open: true, msg: e.message || 'Failed to load Lichess PGN', severity: 'error' });
        return;
      }
    }

    if (!pgnText) {
      setSnackbar({ open: true, msg: t('noPgnData'), severity: 'error' });
      return;
    }

    const parsed = parseGamePgn(pgnText);
    const newGame: OpenedGame = {
      id: gameId,
      white: game.white_name || game.white || '?',
      black: game.black_name || game.black || '?',
      whiteElo: game.white_elo,
      blackElo: game.black_elo,
      result: game.result || '*',
      eco: game.eco,
      date: game.date || game.year?.toString(),
      event: game.event,
      title: game.title ?? undefined,
      pgn: pgnText,
      moves: parsed.moves,
      fens: parsed.fens,
      startingFen: parsed.startingFen,
      source: game.user_id ? 'user' : (game.source || 'twic'),
      readOnly: opts?.readOnly,
      sharedDbToken: opts?.sharedDbToken,
    };

    setOpenedGames(prev => {
      const trimmed = opts?.evictOldestIfFull && prev.length >= 10
        ? prev.slice(prev.length - 9)
        : prev;
      return [...trimmed, newGame];
    });
    // Auto-select the first move on open so the notation has an active cursor
    // and next-move controls advance immediately. Games with no moves
    // fall back to the starting position (-1).
    setGameMoveIndices(prev => ({ ...prev, [gameId]: newGame.moves.length > 0 ? 0 : -1 }));
    setActiveTab(gameId);

    // Track favorite state for user games
    if (game.is_favorite) {
      setFavoriteGameIds(prev => new Set(prev).add(gameId));
    }
  }, [openedGames, setSnackbar, fetchGamePgn]);

  // Fresh empty board tab for recording a variation; auto-save files it in My Games
  // once it has a move or a title.
  const handleAddVariation = useCallback(() => {
    if (openedGames.length >= 10) {
      setSnackbar({ open: true, msg: t('maxTabsError'), severity: 'error' });
      return;
    }
    const id = `new-variation-${Date.now()}`;
    const draft: OpenedGame = {
      id,
      white: '?',
      black: '?',
      result: '*',
      pgn: '',
      moves: [],
      fens: [],
      startingFen: 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1',
      source: 'user',
      isDraft: true,
    };
    setOpenedGames(prev => [...prev, draft]);
    setGameMoveIndices(prev => ({ ...prev, [id]: -1 }));
    setActiveTab(id);
  }, [openedGames.length, t]);

  const handleCloseGame = useCallback((gameId: string, e?: React.MouseEvent) => {
    if (e) e.stopPropagation();
    const closing = openedGames.find(g => g.id === gameId);
    // Closing flushes pending edits (scope change); only a failed save can be lost.
    if (closing && editTreeGameId === gameId && saveStatus === 'error'
      && !window.confirm(t(closing.isDraft ? 'myGames.discardVariationConfirm' : 'myGames.autoSave.unsavedLeaveWarning'))) return;
    setOpenedGames(prev => prev.filter(g => g.id !== gameId));
    setGameMoveIndices(prev => {
      const next = { ...prev };
      delete next[gameId];
      return next;
    });
    if (activeTab === gameId) setActiveTab(lastHomeTabRef.current);
  }, [activeTab, openedGames, editTreeGameId, saveStatus, t]);

  // ─── Deep link: open a shared game from ?g=<slug> (new) or the legacy
  //     ?game=<id>&source=twic. The opaque slug never leaks the data source. ───
  const searchParams = useSearchParams();
  const urlGameHandledRef = useRef(false);
  const mountedRef = useRef(true);
  useEffect(() => {
    mountedRef.current = true;
    return () => { mountedRef.current = false; };
  }, []);
  useEffect(() => {
    if (urlGameHandledRef.current || !searchParams) return;

    // Resolve the deep link: prefer the opaque slug, fall back to legacy params.
    // Stash whatever the URL carries BEFORE the authLoaded early-return below —
    // by the time Clerk loads, the URL-sync effect has already stripped ?g=.
    const slug = searchParams.get('g') ?? pendingShareParams.g;
    const legacyId = searchParams.get('game') ?? pendingShareParams.game;
    const legacySource = searchParams.get('source') ?? pendingShareParams.source;
    pendingShareParams.g = slug;
    pendingShareParams.game = legacyId;
    pendingShareParams.source = legacySource;
    if (!authLoaded) return;

    let target: { source: GameSource; id: number } | null = null;
    if (slug) {
      target = decodeGameSlug(slug);
      if (!target) {
        urlGameHandledRef.current = true;
        clearPendingGameParams();
        setSnackbar({ open: true, msg: t('shareGame.notFound'), severity: 'error' });
        return;
      }
    } else if (legacyId && legacySource === 'twic' && Number.isInteger(Number(legacyId))) {
      target = { source: 'twic', id: Number(legacyId) };
    }
    if (!target) return;

    urlGameHandledRef.current = true;

    // Recipients must be signed in — the single-game PGN endpoint is authed.
    // Rebuild the return URL from the stash: window.location may already have
    // been stripped of the share params.
    if (!isSignedIn) {
      const backParams = new URLSearchParams(window.location.search);
      if (slug) backParams.set('g', slug);
      else if (legacyId) {
        backParams.set('game', legacyId);
        if (legacySource) backParams.set('source', legacySource);
      }
      const back = `${window.location.pathname}?${backParams.toString()}`;
      window.location.assign(`/sign-in?redirect_url=${encodeURIComponent(back)}`);
      return;
    }

    const { source, id } = target;
    const pgnPromise = source === 'lichess'
      ? fetchLichessPgn(String(id))
      : fetchGamePgn(id);

    pgnPromise
      .then((pgn) => {
        // If this instance was unmounted while the PGN was in flight (the page
        // mounts twice on arrival), its state updates would be discarded — keep
        // the stash so the live instance retries instead of opening nothing.
        if (!mountedRef.current) {
          urlGameHandledRef.current = false;
          return;
        }
        clearPendingGameParams();
        const tags = parsePgnHeaders(pgn);
        handleOpenGame({
          id: String(id),
          pgn,
          pgn_offset: 0,
          pgn_length: 0,
          source,
          white_name: tags.White,
          black_name: tags.Black,
          white_elo: tags.WhiteElo ? Number(tags.WhiteElo) : undefined,
          black_elo: tags.BlackElo ? Number(tags.BlackElo) : undefined,
          result: tags.Result,
          eco: tags.ECO,
          date: tags.Date,
          event: tags.Event,
        }, { evictOldestIfFull: true });
      })
      .catch((e: any) => {
        if (!mountedRef.current) {
          urlGameHandledRef.current = false;
          return;
        }
        const status = e?.status;
        if (status === 401 || status === 403 || e?.message === 'Not authenticated') {
          const backParams = new URLSearchParams(window.location.search);
          if (slug) backParams.set('g', slug);
          setSnackbar({ open: true, msg: t('shareGame.signInToView'), severity: 'error' });
          window.location.assign(`/sign-in?redirect_url=${encodeURIComponent(`${window.location.pathname}?${backParams.toString()}`)}`);
        } else if (status === 404) {
          clearPendingGameParams();
          setSnackbar({ open: true, msg: t('shareGame.notFound'), severity: 'error' });
        } else {
          clearPendingGameParams();
          setSnackbar({ open: true, msg: t('shareGame.loadError'), severity: 'error' });
        }
      });
  }, [searchParams, authLoaded, isSignedIn, fetchGamePgn, fetchLichessPgn, handleOpenGame, setSnackbar, t]);

  // ─── Deep link: open a shared *user* game from ?gu=<token>. The token is an
  //     opaque, revocable share token (see /g/u/<token>). Recipients must be
  //     signed in; the fetch endpoint is authed. ───
  const urlSharedGameHandledRef = useRef(false);
  useEffect(() => {
    if (urlSharedGameHandledRef.current || !searchParams) return;
    // Stash before the authLoaded early-return — same remount/strip hazards as
    // the ?g= effect above.
    const token = searchParams.get('gu') ?? pendingShareParams.gu;
    if (!token) return;
    pendingShareParams.gu = token;
    if (!authLoaded) return;
    urlSharedGameHandledRef.current = true;

    const buildBack = () => {
      const backParams = new URLSearchParams(window.location.search);
      backParams.set('gu', token);
      return `${window.location.pathname}?${backParams.toString()}`;
    };

    // Recipients must be signed in — the shared-game endpoint is authed.
    if (!isSignedIn) {
      window.location.assign(`/sign-in?redirect_url=${encodeURIComponent(buildBack())}`);
      return;
    }

    (async () => {
      try {
        const clerkToken = await getToken();
        if (!clerkToken) throw Object.assign(new Error('Not authenticated'), { status: 401 });
        const apiBase = process.env.NEXT_PUBLIC_API_URL || '';
        const game = await apiFetch<Record<string, unknown>>(
          `${apiBase}/api/games/shared/${encodeURIComponent(token)}`,
          { headers: { Authorization: `Bearer ${clerkToken}` } },
        );
        if (!mountedRef.current) {
          urlSharedGameHandledRef.current = false;
          return;
        }
        pendingShareParams.gu = null;
        handleOpenGame(game, { evictOldestIfFull: true });
      } catch (e: unknown) {
        if (!mountedRef.current) {
          urlSharedGameHandledRef.current = false;
          return;
        }
        const status = (e as { status?: number })?.status;
        if (status === 401 || status === 403) {
          setSnackbar({ open: true, msg: t('shareGame.signInToView'), severity: 'error' });
          window.location.assign(`/sign-in?redirect_url=${encodeURIComponent(buildBack())}`);
        } else if (status === 404) {
          pendingShareParams.gu = null;
          setSnackbar({ open: true, msg: t('shareGame.notFound'), severity: 'error' });
        } else {
          pendingShareParams.gu = null;
          setSnackbar({ open: true, msg: t('shareGame.loadError'), severity: 'error' });
        }
      }
    })();
  }, [searchParams, authLoaded, isSignedIn, getToken, handleOpenGame, setSnackbar, t]);

  // ─── Deep link: open a shared *collection* from ?gc=<token>. The token is an
  //     opaque, revocable share token (see /g/c/<token>). Recipients must be
  //     signed in; MyGamesPanel then fetches the collection from the authed
  //     endpoint and renders read-only. Mirrors the ?gu= flow above. ───
  const urlSharedCollectionHandledRef = useRef(false);
  useEffect(() => {
    if (urlSharedCollectionHandledRef.current || !searchParams) return;
    // Stash before the authLoaded early-return — same remount/strip hazards as
    // the ?g= / ?gu= effects above.
    const token = searchParams.get('gc') ?? pendingShareParams.gc;
    if (!token) return;
    pendingShareParams.gc = token;
    if (!authLoaded) return;
    urlSharedCollectionHandledRef.current = true;

    // Recipients must be signed in — the shared-collection endpoint is authed.
    if (!isSignedIn) {
      const backParams = new URLSearchParams(window.location.search);
      backParams.set('gc', token);
      const back = `${window.location.pathname}?${backParams.toString()}`;
      window.location.assign(`/sign-in?redirect_url=${encodeURIComponent(back)}`);
      return;
    }

    pendingShareParams.gc = null;
    setSharedCollectionToken(token);
    setActiveTab('my-games');
  }, [searchParams, authLoaded, isSignedIn]);

  // ─── Deep link: open a shared *database* from ?sdb=<token>. Mirrors ?gc= but
  //     for a single database: records a "Shared with me" subscription (so the
  //     pill persists) then opens the read-only view. Recipients must be signed
  //     in. ───
  const urlSharedDatabaseHandledRef = useRef(false);
  useEffect(() => {
    if (urlSharedDatabaseHandledRef.current || !searchParams) return;
    const token = searchParams.get('sdb') ?? pendingShareParams.sdb;
    if (!token) return;
    pendingShareParams.sdb = token;
    if (!authLoaded) return;
    urlSharedDatabaseHandledRef.current = true;

    if (!isSignedIn) {
      const backParams = new URLSearchParams(window.location.search);
      backParams.set('sdb', token);
      const back = `${window.location.pathname}?${backParams.toString()}`;
      window.location.assign(`/sign-in?redirect_url=${encodeURIComponent(back)}`);
      return;
    }

    pendingShareParams.sdb = null;

    // Record the subscription so the shared pill persists across reloads, then
    // open the read-only view. A revoked/unknown token still opens (the panel
    // shows an "unavailable" state); the subscribe is best-effort.
    (async () => {
      try {
        const clerkToken = await getToken();
        if (clerkToken) {
          const apiBase = process.env.NEXT_PUBLIC_API_URL || '';
          await apiFetch(`${apiBase}/api/databases/shared/${encodeURIComponent(token)}/subscribe`, {
            method: 'POST',
            headers: { Authorization: `Bearer ${clerkToken}` },
          });
        }
      } catch {
        // best-effort — still open the view below
      }
      setSelectedDatabaseId(null);
      setSharedDatabaseToken(token);
      setPillReloadKey(k => k + 1);
      setActiveTab('my-games');
    })();
  }, [searchParams, authLoaded, isSignedIn, getToken]);

  const handleGameMoveChange = useCallback((gameId: string, moveIndex: number) => {
    setGameMoveIndices(prev => ({ ...prev, [gameId]: moveIndex }));
  }, []);

  // ─── URL sync: reflect the active game tab as ?g=<slug> ───
  // Shareable games (twic/lichess) write an opaque slug; other tabs remove it.
  // Other query params (explorer/db) are preserved.
  useEffect(() => {
    if (typeof window === 'undefined') return;
    const params = new URLSearchParams(window.location.search);
    const active = openedGames.find(g => g.id === activeTab);
    let slug: string | null = null;
    if (active) {
      const src = (active.source as string) || 'twic';
      const id = Number(active.id);
      if ((src === 'twic' || src === 'lichess') && Number.isInteger(id) && id >= 0) {
        try { slug = encodeGameSlug(src as GameSource, id); } catch { slug = null; }
      }
    }
    // Never strip an incoming share link that hasn't opened yet — on first
    // mount this effect runs with zero opened games, before the deep-link
    // effect has consumed ?g=.
    if (slug) params.set('g', slug);
    else if (!pendingShareParams.g && !pendingShareParams.game) params.delete('g');
    const qs = params.toString();
    window.history.replaceState({}, '', `${window.location.pathname}${qs ? `?${qs}` : ''}`);
  }, [activeTab, openedGames]);

  const activeGame = openedGames.find(g => g.id === activeTab);
  const activeGameFen = activeGame
    ? (gameMoveIndices[activeGame.id] ?? -1) === -1
      ? activeGame.startingFen
      : activeGame.fens[gameMoveIndices[activeGame.id]] || activeGame.startingFen
    : null;
  // What the board shows — and the engine analyses — on every tab.
  const displayedFen = activeTab === 'my-games' && !activeGame ? myGamesFen : (editTreeFen || activeGameFen || boardFen);

  // Auto-analyze the shown position (any game, line or variation) while enabled.
  useEffect(() => {
    if (stockfishEnabled && isReady) {
      analyze(displayedFen);
    } else if (!stockfishEnabled) {
      stopAnalysis();
    }
  }, [stockfishEnabled, displayedFen, isReady, analyze, stopAnalysis]);

  // ─── Keyboard navigation ───
  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return;
      switch (e.key) {
        case 'ArrowLeft': e.preventDefault(); handlePrev(); break;
        case 'ArrowRight': e.preventDefault(); handleNext(); break;
        case 'Home': e.preventDefault(); handleGoToStart(); break;
        case 'End': e.preventDefault(); handleGoToEnd(); break;
      }
    };
    window.addEventListener('keydown', handleKey);
    return () => window.removeEventListener('keydown', handleKey);
  }, [handlePrev, handleNext, handleGoToStart, handleGoToEnd]);

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', minHeight: { xs: 'auto', lg: '100vh' }, bgcolor: 'var(--surface-page)' }}>
      {/* Backend health warning */}
      {backendHealthy === false && (
        <Box sx={{ px: { xs: 1, sm: 2 }, pt: { xs: 1, sm: 2 } }}>
          <Alert severity="warning" sx={{ borderRadius: 2 }}>
            ♞ Some features may be temporarily unavailable. We&apos;re working on it!
          </Alert>
        </Box>
      )}

      {/* Database switcher (Variation B pill row) — Master (TWIC) + user databases.
          minHeight reserves the first row's height up-front so the async count
          pop-in never shifts the board below it — a shift desyncs chessground's
          cached pointer bounds and taps land one rank off. The row wraps on
          mobile instead of overflowing horizontally. */}
      <Box sx={{ px: { xs: 1, sm: 2 }, pt: { xs: 1, sm: 2 }, minHeight: { xs: 42, sm: 50 }, boxSizing: 'border-box' }}>
        <DatabasePillRow
          masterGameCount={masterDbGameCount}
          selectedDatabaseId={selectedDatabaseId}
          sharedDatabaseToken={sharedDatabaseToken}
          reloadKey={pillReloadKey}
          onSelect={(databaseId, sharedToken) => {
            setSelectedDatabaseId(databaseId);
            setSharedDatabaseToken(sharedToken ?? null);
            // A user/shared database only has a visible effect in the My Games
            // list, so switch to it when one is picked; Master restores default.
            if (databaseId || sharedToken) setActiveTab('my-games');
            else setActiveTab('debut');
          }}
        />
      </Box>

      {/* Mode switcher + Tab bar */}
      <Box sx={{ px: { xs: 1, sm: 2 }, pt: { xs: 1, sm: 2 }, pb: 0 }}>
        {/* Mode tabs hidden — Browse Database disabled for now */}

        {/* Game tabs */}
        {openedGames.length > 0 && (
          <Box sx={{ display: 'flex', gap: 0.5, overflowX: 'auto', pb: 0.5, '&::-webkit-scrollbar': { height: 3 }, '&::-webkit-scrollbar-thumb': { bgcolor: 'var(--text-tertiary)', borderRadius: 2 } }}>
          {openedGames.map(g => (
            <Chip
              key={g.id}
              label={g.title && isVariationGame(g) ? `♟\uFE0E ${g.title}` : g.isDraft ? `♟\uFE0E ${t('myGames.newVariationTab')}` : `♟\uFE0E ${g.white.split(',')[0]} vs ${g.black.split(',')[0]}`}
              onClick={() => setActiveTab(g.id)}
              onDelete={() => handleCloseGame(g.id)}
              deleteIcon={<Close sx={{ fontSize: 14 }} />}
              sx={{
                height: 28, fontSize: 11, maxWidth: 200,
                borderRadius: '9999px',
                bgcolor: activeTab === g.id ? 'primary.main' : 'rgba(255,255,255,0.95)',
                color: activeTab === g.id ? '#fff' : 'var(--text-secondary)',
                border: activeTab === g.id ? 'none' : '1px solid rgba(31,41,55,0.1)',
                '&:hover': { bgcolor: activeTab === g.id ? 'primary.dark' : 'var(--surface-card-hover)' },
                cursor: 'pointer', flexShrink: 0,
                '& .MuiChip-label': { overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' },
                '& .MuiChip-deleteIcon': {
                  color: activeTab === g.id ? '#D1D5DB' : 'var(--text-tertiary)',
                  '&:hover': { color: activeTab === g.id ? '#F3F4F6' : 'var(--text-primary)' },
                },
              }}
            />
          ))}
          </Box>
        )}
      </Box>

      {/* Main content */}
      <Box sx={{
        display: 'flex',
        flexDirection: { xs: 'column', lg: 'row' },
        flex: { xs: 'none', lg: 1 },
        p: { xs: 0, sm: 1, lg: 2 },
        gap: { xs: 0, lg: 2 },
        pb: { xs: 0, md: 2 },
      }}>
        {/* Left: Board + Notation */}
        <Box sx={{
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          flexShrink: 0,
          overflowAnchor: 'none',
          // Desktop: always-on room for the eval bar so it clears the app sidebar.
          pl: { lg: 2 },
        }}>
          {/* Board anchor — the eval bar is pinned outside its left edge, out of flow */}
          <Box data-testid="board-anchor" sx={{ position: 'relative', ml: `${evalBarReserve}px` }}>
            {stockfishEnabled && (
              <StockfishErrorBoundary>
                <Box sx={{ position: 'absolute', top: 0, right: '100%', mr: 0.5 }}>
                <ReplayEvalBar
                  evaluation={evaluation?.lines?.[0] ? { cp: evaluation.lines[0].cp, mate: evaluation.lines[0].mate } : null}
                  isAnalyzing={isAnalyzing}
                  depth={depth}
                  orientation={boardOrientation}
                  height={boardSize}
                  width={EVAL_BAR_WIDTH_PX}
                />
                </Box>
              </StockfishErrorBoundary>
            )}
          <DebutBoard
            fen={displayedFen}
            reservedWidth={evalBarReserve}
            orientation={boardOrientation}
            onMove={activeTab === 'debut' ? handleBoardMove : (isActiveGameEditable ? handleGameBoardMove : (activeTab === 'my-games' && !activeGame ? handleMyGamesBoardMove : (() => {})))}
            onReset={activeTab === 'debut' ? handleReset : (isActiveGameTree ? handleEditTreeGoToStart : (activeTab === 'my-games' && !activeGame ? handleMyGamesReset : () => activeGame && handleGameMoveChange(activeGame.id, -1)))}
            onGoToStart={activeTab === 'debut' ? handleGoToStart : (isActiveGameTree ? handleEditTreeGoToStart : (activeTab === 'my-games' && !activeGame ? handleMyGamesReset : () => activeGame && handleGameMoveChange(activeGame.id, -1)))}
            onPrev={activeTab === 'debut' ? handlePrev : (isActiveGameTree ? handleEditTreePrev : (activeTab === 'my-games' && !activeGame ? handleMyGamesPrev : () => activeGame && handleGameMoveChange(activeGame.id, Math.max(-1, (gameMoveIndices[activeGame.id] ?? -1) - 1))))}
            onNext={activeTab === 'debut' ? handleNext : (isActiveGameTree ? handleEditTreeNext : (activeTab === 'my-games' && !activeGame ? handleMyGamesNext : () => activeGame && handleGameMoveChange(activeGame.id, Math.min((activeGame?.moves.length ?? 1) - 1, (gameMoveIndices[activeGame.id] ?? -1) + 1))))}
            onGoToEnd={activeTab === 'debut' ? handleGoToEnd : (isActiveGameTree ? handleEditTreeGoToEnd : (activeTab === 'my-games' && !activeGame ? handleMyGamesGoToEnd : () => activeGame && handleGameMoveChange(activeGame.id, (activeGame?.moves.length ?? 1) - 1)))}
            onFlip={handleFlip}
            squareBadge={activeTab !== 'debut' && activeGame ? editTreeBadge : null}
          />
          </Box>

          {/* My Games move list — below board when on My Games tab with no game open */}
          {activeTab === 'my-games' && !activeGame && (
            <MyGamesMoveList
              moves={myGamesSanMoves}
              currentIndex={myGamesMoveIndex}
              comments={myGamesComments}
              onNavigate={(index) => setMyGamesMoveIndex(index)}
              onComment={handleMyGamesComment}
              onDeleteMove={handleMyGamesDeleteMove}
            />
          )}

          {/* Every opened game with moves is reviewable, whatever its source. */}
          {activeTab !== 'debut' && activeGame && reviewPgn && (
            <Box sx={{
              width: { xs: 'calc(100% - 32px)', sm: 'calc(100% - 24px)', lg: 520 },
              maxWidth: 520,
              mx: 'auto',
              mt: 1,
              display: 'flex',
              justifyContent: 'center',
            }}>
              <StartReviewButton
                game={{ pgn: reviewPgn, orientation: boardOrientation }}
                source="database"
                variant="primary"
                style={{ width: '100%' }}
              />
            </Box>
          )}

          {/* Stockfish toggle + engine lines — every tab, game and line */}
          <Box sx={{
            width: { xs: 'calc(100% - 32px)', sm: 'calc(100% - 24px)', lg: 520 },
            maxWidth: 520,
            mx: 'auto',
            mt: 0.5,
            overflowAnchor: 'none',
          }}>
            {/* Toggle row */}
            <Box
              onClick={toggleStockfish}
              sx={{
                display: 'flex', alignItems: 'center', gap: 1,
                px: 1.5, py: 0.75,
                cursor: 'pointer', userSelect: 'none',
                bgcolor: stockfishEnabled ? 'rgba(0,0,0,0.04)' : 'transparent',
                borderRadius: '12px',
                transition: 'background 0.15s',
                '&:hover': { bgcolor: 'rgba(0,0,0,0.06)' },
              }}
            >
              <Box sx={{
                width: 8, height: 8, borderRadius: '50%',
                bgcolor: stockfishEnabled ? (isAnalyzing ? '#71717A' : '#22c55e') : '#9ca3af',
                transition: 'background 0.15s',
                ...(isAnalyzing && stockfishEnabled ? { animation: 'pulse 1.5s ease-in-out infinite' } : {}),
              }} />
              <Typography variant="caption" sx={{ fontWeight: 600, color: stockfishEnabled ? 'var(--text-primary)' : 'var(--text-tertiary)', fontSize: 12 }}>
                {engineVariantLabel(engineName)}
              </Typography>
              {stockfishEnabled && depth > 0 && (
                <Typography variant="caption" sx={{ color: 'var(--text-tertiary)', fontFamily: 'monospace', fontSize: 11 }}>
                  · d{depth}
                </Typography>
              )}
              <EngineSettingsMenu />
              <Box sx={{ flexGrow: 1 }} />
              <Switch
                size="small"
                checked={stockfishEnabled}
                onChange={toggleStockfish}
                onClick={(e) => e.stopPropagation()}
                sx={{
                  '& .MuiSwitch-switchBase.Mui-checked': { color: '#52525B' },
                  '& .MuiSwitch-switchBase.Mui-checked + .MuiSwitch-track': { backgroundColor: '#A1A1AA' },
                }}
              />
            </Box>

            <StockfishErrorBoundary>
              {/* Engine error message */}
              {engineError && (
                <Box sx={{ mt: 0.5, px: 1.5, py: 0.75, bgcolor: 'rgba(220,38,38,0.08)', border: '1px solid rgba(220,38,38,0.2)', borderRadius: '10px' }}>
                  <Typography sx={{ fontSize: 12, color: '#dc2626' }}>
                    Engine not available: {engineError}
                  </Typography>
                </Box>
              )}

              {/* Engine lines */}
              {stockfishEnabled && !engineError && (
                <Box sx={{ mt: 0.5 }}>
                  <ReplayEngineLines
                    lines={evaluation?.lines ?? []}
                    currentFen={displayedFen}
                    maxLines={engineLines}
                  />
                </Box>
              )}
            </StockfishErrorBoundary>
          </Box>

          {/* Game viewer notation — below board on small screens only */}
          {activeTab !== 'debut' && activeGame && (
            <Box sx={{
              display: { xs: 'block', lg: 'none' },
              width: '100%',
              maxWidth: { xs: '100%' },
            }}>
              <GameViewerPanel
                game={activeGame}
                currentMoveIndex={gameMoveIndices[activeGame.id] ?? -1}
                onMoveIndexChange={(idx) => handleGameMoveChange(activeGame.id, idx)}
                onSaveToMyGames={activeGame.isDraft ? undefined : handleSaveToMyGames}
                isSaved={savedGameIds.has(activeGame.id)}
                onEditGame={isActiveGameEditable && !activeGame.isDraft ? () => handleEditGameFromViewer(activeGame) : undefined}
                onToggleFavorite={isActiveGameEditable && !activeGame.isDraft ? handleViewerToggleFavorite : undefined}
                onDeleteGame={isActiveGameEditable && !activeGame.isDraft ? handleViewerDeleteGame : undefined}
                onTitleChange={isActiveGameEditable ? (title) => handleVariationTitleChange(activeGame, title) : undefined}
                isFavorite={favoriteGameIds.has(activeGame.id)}
                isEditable={isActiveGameEditable}
                editTree={isActiveGameTree ? gameMoveTree.tree : undefined}
                editSelectedNodeId={isActiveGameTree ? editTreeSelectedNodeId : undefined}
                onEditNodeSelect={isActiveGameTree ? handleEditNodeSelect : undefined}
                onEditSave={isActiveGameEditable ? handleEditTreeSaveNow : undefined}
                editIsDirty={isActiveGameEditable ? editTreeHasUnsaved : undefined}
                saveStatus={isActiveGameEditable ? saveStatus : undefined}
                onRetrySave={isActiveGameEditable ? handleRetrySave : undefined}
                editContextMenuActions={editContextMenuActions}
                voiceNotes={voicePlayback}
                onTreePrev={isActiveGameTree ? handleEditTreePrev : undefined}
                onTreeNext={isActiveGameTree ? handleEditTreeNext : undefined}
                onTreeGoToStart={isActiveGameTree ? handleEditTreeGoToStart : undefined}
                onTreeGoToEnd={isActiveGameTree ? handleEditTreeGoToEnd : undefined}
              />
            </Box>
          )}
        </Box>

        {/* Right: Master explorer / My Games / game viewer */}
        <Box sx={{
          flex: { xs: 'none', lg: 1 },
          display: 'flex',
          flexDirection: 'column',
          bgcolor: { xs: 'transparent', lg: 'var(--surface-card)' },
          borderRadius: { xs: 0, lg: '24px' },
          border: { xs: 'none', lg: '1px solid rgba(31,41,55,0.1)' },
          overflow: { xs: 'visible', lg: 'hidden' },
          minWidth: 0,
          maxHeight: { lg: 'calc(100vh - 32px)' },
        }}>
          {activeTab === 'debut' ? (
            <Box sx={{ flex: 1, overflow: 'auto' }}>
              {/* Move Tree (ChessBase-style) */}
              <MoveTree
                moves={displayedMoves}
                totalGames={displayedTotalGames}
                loading={displayedLoading}
                onMoveClick={handleMoveTreeClick}
                fen={boardFen}
                source={moveTreeSource}
                onSourceChange={setMoveTreeSource}
              />

              {/* Position Summary (ECO + aggregate W/D/L) */}
              <PositionSummary
                ecoCode={masterOpening?.eco ?? null}
                openingName={masterOpening?.name ?? null}
                totalGames={candidatesTotalGames}
                moves={candidateMoves}
              />

              {/* Master Games */}
              <MasterGamesPanel
                fen={boardFen}
                masterGames={masterGames}
                masterGamesTotal={masterGamesTotal}
                masterGamesLoading={masterGamesLoading}
                onOpenGame={handleOpenGame}
                masterGamesFilters={masterGamesFilters}
                onMasterGamesFilterChange={setMasterGamesFilters}
                explorerTab={explorerTab}
                onExplorerTabChange={setExplorerTab}
                lichessDatabase={lichessDatabase}
                onLichessDatabaseChange={setLichessDatabase}
              />
            </Box>
          ) : activeTab === 'my-games' ? (
            <Box sx={{ flex: 1, overflow: 'auto' }}>
              <MyGamesPanel
                onOpenGame={(game) => handleOpenGame(game, sharedDatabaseToken
                  ? { readOnly: true, sharedDbToken: sharedDatabaseToken }
                  : sharedCollectionToken ? { readOnly: true } : undefined)}
                boardPgn={buildMyGamesPgn()}
                boardHasMoves={myGamesSanMoves.length > 0}
                onBoardReset={handleMyGamesReset}
                sharedToken={sharedCollectionToken ?? undefined}
                sharedDatabaseToken={sharedDatabaseToken ?? undefined}
                databaseId={selectedDatabaseId ?? undefined}
                onAddVariation={handleAddVariation}
                refreshKey={myGamesRefreshKey}
                onCopyShared={(db) => {
                  // Copied → switch to the new owned pill and refresh the row.
                  setSharedDatabaseToken(null);
                  setSelectedDatabaseId(db.id);
                  setPillReloadKey(k => k + 1);
                  setActiveTab('my-games');
                  setSnackbar({ open: true, msg: t('myGames.copiedShared', { name: db.name }), severity: 'success' });
                }}
              />
            </Box>
          ) : activeGame ? (
            <Box sx={{ display: { xs: 'none', lg: 'flex' }, flex: 1, flexDirection: 'column', overflow: 'auto' }}>
              <GameViewerPanel
                game={activeGame}
                currentMoveIndex={gameMoveIndices[activeGame.id] ?? -1}
                onMoveIndexChange={(idx) => handleGameMoveChange(activeGame.id, idx)}
                onSaveToMyGames={activeGame.isDraft ? undefined : handleSaveToMyGames}
                isSaved={savedGameIds.has(activeGame.id)}
                onEditGame={isActiveGameEditable && !activeGame.isDraft ? () => handleEditGameFromViewer(activeGame) : undefined}
                onToggleFavorite={isActiveGameEditable && !activeGame.isDraft ? handleViewerToggleFavorite : undefined}
                onDeleteGame={isActiveGameEditable && !activeGame.isDraft ? handleViewerDeleteGame : undefined}
                onTitleChange={isActiveGameEditable ? (title) => handleVariationTitleChange(activeGame, title) : undefined}
                isFavorite={favoriteGameIds.has(activeGame.id)}
                isEditable={isActiveGameEditable}
                editTree={isActiveGameTree ? gameMoveTree.tree : undefined}
                editSelectedNodeId={isActiveGameTree ? editTreeSelectedNodeId : undefined}
                onEditNodeSelect={isActiveGameTree ? handleEditNodeSelect : undefined}
                onEditSave={isActiveGameEditable ? handleEditTreeSaveNow : undefined}
                editIsDirty={isActiveGameEditable ? editTreeHasUnsaved : undefined}
                saveStatus={isActiveGameEditable ? saveStatus : undefined}
                onRetrySave={isActiveGameEditable ? handleRetrySave : undefined}
                editContextMenuActions={editContextMenuActions}
                voiceNotes={voicePlayback}
              />
            </Box>
          ) : null}
        </Box>
      </Box>

      {/* Modals */}
      <EditGameModal
        open={editModalOpen}
        onClose={() => { setEditModalOpen(false); setEditingGame(null); }}
        game={editingGame}
        onSave={handleEditGameSave}
      />

      {/* Snackbar */}
      <Snackbar
        open={snackbar.open}
        autoHideDuration={4000}
        onClose={() => setSnackbar(s => ({ ...s, open: false }))}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}
      >
        <Alert severity={snackbar.severity} onClose={() => setSnackbar(s => ({ ...s, open: false }))} sx={{ width: '100%' }}>
          {snackbar.msg}
        </Alert>
      </Snackbar>
    </Box>
  );
}
