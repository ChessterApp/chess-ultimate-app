'use client';

import { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { useTranslations } from 'next-intl';
import { Box, Typography, Snackbar, Alert, Chip, Switch } from '@mui/material';
import { useBackendHealth } from '@/hooks/useBackendHealth';
import dynamic from 'next/dynamic';
import { Chess } from 'chess.js';
// Import chessground CSS at page level to ensure it's included in the page's CSS bundle
// (dynamic imports with ssr:false may not reliably load CSS chunks in turbopack)
import 'chessground/assets/chessground.base.css';
import 'chessground/assets/chessground.brown.css';
import '@/styles/chessground-theme.css';
import { useOpeningRepertoire } from '@/hooks/useOpeningRepertoire';
import type { OpeningNode, GameSearchResult, GameLink, MoveCandidate, CandidatesResponse } from '@/hooks/useOpeningRepertoire';
import type { Key } from 'chessground/types';
import type { ExplorerTab } from '@/components/openings/ExplorerTabs';
import type { MoveTreeSource } from '@/components/openings/MoveTree';
import type { MasterGamesFilterState } from '@/components/openings/MasterGamesFilter';
import { useLichessExplorer } from '@/hooks/useLichessExplorer';
import { useReplayStockfish } from '@/hooks/useReplayStockfish';

// Dynamic imports to avoid SSR issues
const DebutBoard = dynamic(() => import('@/components/openings/DebutBoard'), {
  ssr: false,
  loading: () => <div className="animate-pulse h-80 bg-stone-200 rounded-xl" />
});
const RepertoireSelector = dynamic(() => import('@/components/openings/RepertoireSelector'), {
  ssr: false,
  loading: () => <div className="animate-pulse h-16 bg-stone-200 rounded-xl" />
});
const MoveNotation = dynamic(() => import('@/components/openings/MoveNotation'), {
  ssr: false,
  loading: () => <div className="animate-pulse h-20 bg-stone-200 rounded-xl" />
});
const NodeDetailsPanel = dynamic(() => import('@/components/openings/NodeDetailsPanel'), {
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
const PgnImporter = dynamic(() => import('@/components/openings/PgnImporter'), {
  ssr: false,
  loading: () => null
});
const GameSearchPanel = dynamic(() => import('@/components/openings/GameSearchPanel'), {
  ssr: false,
  loading: () => null
});
const TwicExplorer = dynamic(() => import('@/components/analysis/TwicExplorer'), {
  ssr: false,
  loading: () => <div className="animate-pulse h-96 bg-stone-200 rounded-xl" />
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

import type { OpenedGame } from '@/components/openings/GameViewerPanel';
import { parseGamePgn } from '@/components/openings/GameViewerPanel';
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
import type { MoveContextMenuActions } from '@/components/openings/MoveNotation';
import { Close, FolderOpen } from '@mui/icons-material';

const STARTING_FEN = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1';

export default function DebutPage() {
  const t = useTranslations('debut');
  // Auth disabled
  const session = { isLoaded: true, isSignedIn: true };
  const backendHealthy = useBackendHealth();

  // mounted guard removed — dynamic imports with ssr:false handle this

  // ─── Mode state ───
  const [mode, setMode] = useState<'repertoire' | 'browse'>('repertoire');

  // ─── Core state ───
  const [selectedRepertoireId, setSelectedRepertoireId] = useState<string | null>(null);
  const [selectedNode, setSelectedNode] = useState<OpeningNode | null>(null);
  const [boardFen, setBoardFen] = useState(STARTING_FEN);
  const [boardOrientation, setBoardOrientation] = useState<'white' | 'black'>('white');

  // ─── Browse mode state ───
  const [browseFen, setBrowseFen] = useState(STARTING_FEN);
  const [browseMoveHistory, setBrowseMoveHistory] = useState<Array<{ san: string; fen: string }>>([]);

  // ─── My Games tab board interaction state ───
  const [myGamesMoveHistory, setMyGamesMoveHistory] = useState<string[]>([STARTING_FEN]);
  const [myGamesMoveIndex, setMyGamesMoveIndex] = useState(0);
  const [myGamesSanMoves, setMyGamesSanMoves] = useState<string[]>([]);
  const [myGamesComments, setMyGamesComments] = useState<Record<number, string>>({});

  // ─── Modal state ───
  const [pgnImporterOpen, setPgnImporterOpen] = useState(false);
  const [gameSearchOpen, setGameSearchOpen] = useState(false);
  const [gameSearchFen, setGameSearchFen] = useState(STARTING_FEN);

  // ─── Game links ───
  const [gameLinks, setGameLinks] = useState<GameLink[]>([]);
  const [gameLinksLoading, setGameLinksLoading] = useState(false);

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


  // ─── Game viewer tabs ───
  const [openedGames, setOpenedGames] = useState<OpenedGame[]>([]);
  const [activeTab, setActiveTab] = useState<string>('debut');
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
  const { evaluation, isAnalyzing, isReady, depth, analyze, stopAnalysis } = useReplayStockfish({ enabled: stockfishEnabled });

  // Auto-analyze when position changes and Stockfish is enabled
  useEffect(() => {
    if (stockfishEnabled && activeTab === 'debut' && isReady) {
      analyze(boardFen);
    } else if (!stockfishEnabled) {
      stopAnalysis();
    }
  }, [stockfishEnabled, boardFen, activeTab, isReady, analyze, stopAnalysis]);

  const toggleStockfish = useCallback(() => {
    setStockfishEnabled(prev => !prev);
  }, []);

  // ─── Board size (mirrors DebutBoard logic for eval bar height) ───
  const [windowWidth, setWindowWidth] = useState(typeof window !== 'undefined' ? window.innerWidth : 1024);
  useEffect(() => {
    const handleResize = () => setWindowWidth(window.innerWidth);
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);
  const boardSize = useMemo(() => {
    if (windowWidth < 400) return Math.min(windowWidth - 32, 320);
    if (windowWidth < 600) return Math.min(windowWidth - 24, 360);
    if (windowWidth < 768) return Math.min(windowWidth - 32, 420);
    if (windowWidth < 1024) return Math.min(windowWidth - 48, 480);
    return 520;
  }, [windowWidth]);

  // ─── Best Stockfish line (UCI → SAN + eval text) ───
  const bestLine = useMemo(() => {
    if (!evaluation?.lines?.[0]) return null;
    const line = evaluation.lines[0];
    const sanMoves: string[] = [];
    try {
      const chess = new Chess(boardFen);
      const movesToShow = Math.min(line.pv.length, 8);
      for (let i = 0; i < movesToShow; i++) {
        const uci = line.pv[i];
        if (!uci) break;
        try {
          const move = chess.move({ from: uci.slice(0, 2), to: uci.slice(2, 4), promotion: uci.length > 4 ? uci[4] : undefined });
          if (move) sanMoves.push(move.san);
          else break;
        } catch { break; }
      }
    } catch {}
    let evalText = '0.00';
    if (line.mate !== undefined) evalText = line.mate > 0 ? `+M${line.mate}` : `-M${Math.abs(line.mate)}`;
    else if (line.cp !== undefined) { const p = line.cp / 100; evalText = p >= 0 ? `+${p.toFixed(1)}` : p.toFixed(1); }
    return { evalText, sanMoves };
  }, [evaluation, boardFen]);

  // ─── Snackbar ───
  const [snackbar, setSnackbar] = useState<{ open: boolean; msg: string; severity: 'success' | 'error' }>({ open: false, msg: '', severity: 'success' });

  // ─── My Games (save bookmark + edit) ───
  const { createGame: createUserGame, updateGame: updateUserGame, toggleFavorite: toggleUserFavorite, deleteGame: deleteUserGame } = useUserGames();
  const [savedGameIds, setSavedGameIds] = useState<Set<string>>(new Set());
  const [favoriteGameIds, setFavoriteGameIds] = useState<Set<string>>(new Set());
  const [editModalOpen, setEditModalOpen] = useState(false);
  const [editingGame, setEditingGame] = useState<UserGame | null>(null);

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

  const handleViewerDeleteGame = useCallback(async () => {
    if (!activeTab) return;
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
  }, [activeTab, deleteUserGame]);

  // ─── Game move tree: init when opening a user game ───
  const activeGameForTree = openedGames.find(g => g.id === activeTab);
  const isActiveGameEditable = activeGameForTree?.source === 'user';

  // Initialize tree when switching to a user game tab
  useEffect(() => {
    if (isActiveGameEditable && activeGameForTree && editTreeGameId !== activeGameForTree.id) {
      gameMoveTree.initFromPgn(activeGameForTree.pgn);
      setEditTreeGameId(activeGameForTree.id);
      setEditTreeSelectedNodeId(null);
    }
  }, [isActiveGameEditable, activeGameForTree?.id, activeGameForTree?.pgn, editTreeGameId, gameMoveTree]);

  const handleEditNodeSelect = useCallback((node: OpeningNode) => {
    setEditTreeSelectedNodeId(node.id);
  }, []);

  const handleGameBoardMove = useCallback((
    from: string, to: string, piece: string, newFen: string, moveSan: string, moveUci: string
  ) => {
    if (!gameMoveTree.tree || !editTreeSelectedNodeId) {
      // If no node selected, try to add from root
      if (gameMoveTree.tree) {
        const result = gameMoveTree.addMove(gameMoveTree.tree.id, moveSan, moveUci, newFen);
        if (result) setEditTreeSelectedNodeId(result.id);
      }
      return;
    }

    // Check if current node already has this move as a child
    const currentNode = findGameTreeNode(gameMoveTree.tree, editTreeSelectedNodeId);
    if (!currentNode) return;

    const fenKey = newFen.split(' ').slice(0, 4).join(' ');
    const existing = (currentNode.children || []).find(
      c => c.fen.split(' ').slice(0, 4).join(' ') === fenKey
    );

    if (existing) {
      // Navigate to existing child
      setEditTreeSelectedNodeId(existing.id);
    } else {
      // Add new move (may create variation)
      const result = gameMoveTree.addMove(currentNode.id, moveSan, moveUci, newFen);
      if (result) setEditTreeSelectedNodeId(result.id);
    }
  }, [gameMoveTree, editTreeSelectedNodeId]);

  const handleEditTreeSave = useCallback(async () => {
    if (!activeGameForTree || !gameMoveTree.isDirty) return;
    const newPgn = gameMoveTree.getPgn();
    const result = await updateUserGame(activeGameForTree.id, { pgn: newPgn });
    if (result) {
      // Update the opened game with new PGN + re-parsed moves
      const parsed = parseGamePgn(newPgn);
      setOpenedGames(prev => prev.map(g => {
        if (g.id !== activeGameForTree.id) return g;
        return { ...g, pgn: newPgn, moves: parsed.moves, fens: parsed.fens };
      }));
      gameMoveTree.markClean();
      setSnackbar({ open: true, msg: t('myGames.moveEdit.savedSuccessfully'), severity: 'success' });
    } else {
      setSnackbar({ open: true, msg: t('myGames.editModal.updateFailed'), severity: 'error' });
    }
  }, [activeGameForTree, gameMoveTree, updateUserGame, t]);

  const editContextMenuActions: MoveContextMenuActions | undefined = isActiveGameEditable ? {
    onDeleteFromHere: (node) => {
      gameMoveTree.deleteFromHere(node.id);
      // Navigate to parent
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
    onDeleteVariation: (node) => {
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
    labels: {
      deleteFromHere: t('myGames.moveEdit.deleteFromHere'),
      deleteVariation: t('myGames.moveEdit.deleteVariation'),
      promoteVariation: t('myGames.moveEdit.promoteVariation'),
      makeMainLine: t('myGames.moveEdit.makeMainLine'),
    },
  } : undefined;

  // Get the FEN for the selected tree node (when viewing an editable game)
  const editTreeFen = useMemo(() => {
    if (!isActiveGameEditable || !gameMoveTree.tree || !editTreeSelectedNodeId) {
      return null;
    }
    const node = findGameTreeNode(gameMoveTree.tree, editTreeSelectedNodeId);
    return node?.fen || null;
  }, [isActiveGameEditable, gameMoveTree.tree, editTreeSelectedNodeId]);

  // ─── Tree navigation callbacks (for DebutBoard arrows + keyboard in tree mode) ───
  const handleEditTreePrev = useCallback(() => {
    if (!gameMoveTree.tree || !editTreeSelectedNodeId) return;
    const parent = findGameTreeParent(gameMoveTree.tree, editTreeSelectedNodeId);
    if (parent) setEditTreeSelectedNodeId(parent.id);
  }, [gameMoveTree.tree, editTreeSelectedNodeId]);

  const handleEditTreeNext = useCallback(() => {
    if (!gameMoveTree.tree || !editTreeSelectedNodeId) return;
    const node = findGameTreeNode(gameMoveTree.tree, editTreeSelectedNodeId);
    if (node?.children?.length) setEditTreeSelectedNodeId(node.children[0].id);
  }, [gameMoveTree.tree, editTreeSelectedNodeId]);

  const handleEditTreeGoToStart = useCallback(() => {
    if (!gameMoveTree.tree) return;
    setEditTreeSelectedNodeId(gameMoveTree.tree.id);
  }, [gameMoveTree.tree]);

  const handleEditTreeGoToEnd = useCallback(() => {
    if (!gameMoveTree.tree || !editTreeSelectedNodeId) return;
    let node = findGameTreeNode(gameMoveTree.tree, editTreeSelectedNodeId);
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

  // ─── Hook ───
  const {
    repertoires, loading, error, fetchRepertoires,
    createRepertoire, updateRepertoire, deleteRepertoire,
    currentTree, setCurrentTree, treeLoading, fetchTree,
    addNode, updateNode, deleteNode,
    importPgn, exportPgn,
    addArrow, deleteArrow,
    fetchGamesByPosition, fetchPositionCount, fetchGamePgn, fetchLichessPgn,
    searchGamesStream, linkGame, getNodeGames, deleteGameLink,
    fetchCandidateMoves,
  } = useOpeningRepertoire();

  // ─── Lichess Explorer for move tree ───
  const lichessExplorerFen = moveTreeSource !== 'twic' && selectedNode ? selectedNode.fen : '';
  const lichessExplorerDb = moveTreeSource === 'lichess-masters' ? 'masters' : 'lichess';
  const { data: lichessExplorerData, loading: lichessExplorerLoading } = useLichessExplorer({
    fen: lichessExplorerFen,
    database: lichessExplorerDb,
    enabled: moveTreeSource !== 'twic' && !!selectedNode,
  });

  // ─── Refs for temp ID tracking and move queue ───
  const tempToRealIdRef = useRef<Map<string, string>>(new Map());
  const moveQueueRef = useRef<Array<{ from: string; to: string; piece: string; newFen: string; moveSan: string; moveUci: string }>>(
    []
  );
  const isProcessingMoveRef = useRef(false);

  // ─── Refs for latest state (used by move queue to avoid stale closures) ───
  const selectedNodeRef = useRef(selectedNode);
  selectedNodeRef.current = selectedNode;
  const currentTreeRef = useRef(currentTree);
  currentTreeRef.current = currentTree;

  // ─── Fetch repertoires on mount ───
  useEffect(() => { fetchRepertoires(); }, [fetchRepertoires]);

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

  // ─── Auto-select first repertoire ───
  useEffect(() => {
    if (repertoires.length > 0 && !selectedRepertoireId) {
      setSelectedRepertoireId(repertoires[0].id);
    }
  }, [repertoires, selectedRepertoireId]);

  // ─── Track selected node by ID (survives tree re-fetches) ───
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);

  // ─── Fetch tree when repertoire changes ───
  useEffect(() => {
    if (selectedRepertoireId) {
      fetchTree(selectedRepertoireId);
      const rep = repertoires.find(r => r.id === selectedRepertoireId);
      if (rep) {
        setBoardOrientation(rep.color === 'b' ? 'black' : 'white');
        setBoardFen(rep.starting_fen || STARTING_FEN);
        setSelectedNode(null);
        setSelectedNodeId(null);
      }
    }
  }, [selectedRepertoireId, fetchTree, repertoires]);

  // ─── Re-resolve selectedNode from tree whenever tree or selectedNodeId changes ───
  useEffect(() => {
    if (!currentTree) {
      setSelectedNode(null);
      return;
    }
    if (!selectedNodeId) {
      // No node requested — select root
      setSelectedNode(currentTree);
      setBoardFen(currentTree.fen);
      return;
    }
    // Find node by ID in the fresh tree
    const findById = (node: OpeningNode, id: string): OpeningNode | null => {
      if (node.id === id) return node;
      for (const child of node.children || []) {
        const found = findById(child, id);
        if (found) return found;
      }
      return null;
    };
    const resolved = findById(currentTree, selectedNodeId);
    if (resolved) {
      setSelectedNode(resolved);
      setBoardFen(resolved.fen);
    }
    // If not found, DON'T reset to root — the node might be newly created
    // and not yet in the tree (fetchTree still in flight). The next tree
    // update will resolve it. Only reset if we have no selectedNode at all.
    else if (!selectedNode) {
      setSelectedNode(currentTree);
      setBoardFen(currentTree.fen);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentTree, selectedNodeId]);

  // ─── Load game links when node changes ───
  useEffect(() => {
    if (selectedNode && selectedNode.move_san !== null && !selectedNode.id.startsWith('temp-')) {
      setGameLinksLoading(true);
      getNodeGames(selectedNode.id)
        .then(setGameLinks)
        .catch(() => setGameLinks([]))
        .finally(() => setGameLinksLoading(false));
    } else {
      setGameLinks([]);
    }
  }, [selectedNode?.id, getNodeGames]);

  // ─── Auto-fetch master games when node or filters change ───
  useEffect(() => {
    if (!selectedNode) {
      setMasterGames([]);
      setMasterGamesTotal(0);
      return;
    }

    let cancelled = false;
    setMasterGamesLoading(true);

    fetchGamesByPosition(
      selectedNode.fen,
      50,
      masterGamesFilters.playerColor,
      masterGamesFilters.playerName,
      masterGamesFilters.sortBy,
      masterGamesFilters.opponentName,
      masterGamesFilters.result,
      masterGamesFilters.whiteEloMin,
      masterGamesFilters.whiteEloMax,
      masterGamesFilters.blackEloMin,
      masterGamesFilters.blackEloMax,
      masterGamesFilters.dateFrom,
      masterGamesFilters.dateTo,
      masterGamesFilters.ecoCode,
      masterGamesFilters.eventName
    )
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
          setMasterGamesTotal(data.total);

          // If count is approximate, fetch exact count in background
          if (!data.count_exact && data.games.length > 0) {
            fetchPositionCount(selectedNode.fen)
              .then((count) => { if (!cancelled) setMasterGamesTotal(count); })
              .catch(() => {});
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
  }, [selectedNode?.fen, masterGamesFilters.playerColor, masterGamesFilters.playerName, masterGamesFilters.sortBy, masterGamesFilters.opponentName, masterGamesFilters.result, masterGamesFilters.whiteEloMin, masterGamesFilters.whiteEloMax, masterGamesFilters.blackEloMin, masterGamesFilters.blackEloMax, masterGamesFilters.dateFrom, masterGamesFilters.dateTo, masterGamesFilters.ecoCode, masterGamesFilters.eventName, fetchGamesByPosition, fetchPositionCount]);

  // ─── Auto-fetch candidate moves when node changes ───
  useEffect(() => {
    if (!selectedNode) {
      setCandidateMoves([]);
      setCandidatesTotalGames(0);
      return;
    }

    // Only fetch TWIC data if using TWIC source
    if (moveTreeSource !== 'twic') {
      setCandidateMoves([]);
      setCandidatesTotalGames(0);
      return;
    }

    let cancelled = false;
    setCandidatesLoading(true);

    fetchCandidateMoves(selectedNode.fen)
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
  }, [selectedNode?.fen, fetchCandidateMoves, moveTreeSource]);

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

  const handleNodeSelect = useCallback((node: OpeningNode) => {
    setSelectedNodeId(node.id);
    setSelectedNode(node);
    setBoardFen(node.fen);
    setMasterGamesFilters({
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
  }, []);

  // Find node by id in tree
  const findNode = useCallback((tree: OpeningNode | null, id: string): OpeningNode | null => {
    if (!tree) return null;
    if (tree.id === id) return tree;
    for (const child of tree.children || []) {
      const found = findNode(child, id);
      if (found) return found;
    }
    return null;
  }, []);

  // Find main line (first child path) to deepest node
  const findDeepestMainLine = useCallback((node: OpeningNode): OpeningNode => {
    if (!node.children?.length) return node;
    return findDeepestMainLine(node.children[0]);
  }, []);

  // ── Process queued moves sequentially, reading FRESH state from refs ──
  const processQueue = useCallback(async () => {
    if (isProcessingMoveRef.current) return;
    isProcessingMoveRef.current = true;

    while (moveQueueRef.current.length > 0) {
      const move = moveQueueRef.current.shift()!;
      const { newFen, moveSan, moveUci } = move;

      // Read FRESH state from refs (not stale closure)
      const curSelectedNode = selectedNodeRef.current;
      const curTree = currentTreeRef.current;
      if (!curSelectedNode || !selectedRepertoireId || !curTree) continue;

      const newFenParts = newFen.split(' ').slice(0, 4).join(' ');
      const fenMatch = (c: OpeningNode) => c.fen.split(' ').slice(0, 4).join(' ') === newFenParts;

      // Check if child with this FEN already exists
      let existingChild = curSelectedNode.children?.find(fenMatch) || null;
      if (!existingChild) {
        const findInTree = (node: OpeningNode, id: string): OpeningNode | null => {
          if (node.id === id) return node;
          for (const ch of node.children || []) { const f = findInTree(ch, id); if (f) return f; }
          return null;
        };
        const treeParent = findInTree(curTree, curSelectedNode.id);
        existingChild = treeParent?.children?.find(fenMatch) || null;
      }

      if (existingChild) {
        setSelectedNodeId(existingChild.id);
        setSelectedNode(existingChild);
        setBoardFen(existingChild.fen);
        continue;
      }

      // Build optimistic node
      const fenParts = newFen.split(' ');
      const isWhiteMove = fenParts[1] === 'b';
      const moveNumber = parseInt(fenParts[5]) - (isWhiteMove ? 0 : 1);
      const tempId = `temp-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`;

      const optimisticNode: OpeningNode = {
        id: tempId,
        repertoire_id: selectedRepertoireId,
        parent_id: curSelectedNode.id,
        fen: newFen,
        move_san: moveSan,
        move_uci: moveUci,
        move_number: moveNumber || 1,
        is_white_move: isWhiteMove,
        opening_name: null,
        eco_code: null,
        notes: null,
        priority: 1,
        is_critical: false,
        times_trained: 0,
        times_correct: 0,
        last_trained_at: null,
        next_review_at: null,
        ease_factor: 2.5,
        interval_days: 0,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        children: [],
      };

      // Clone tree and insert as first child (main line) if no existing children,
      // or as last child (variation) if parent already has children
      const cloneAndInsert = (node: OpeningNode): OpeningNode => {
        const cloned = { ...node, children: (node.children || []).map(cloneAndInsert) };
        if (node.id === curSelectedNode.id) {
          const alreadyHasFen = (cloned.children || []).some(fenMatch);
          if (!alreadyHasFen) {
            if ((cloned.children || []).length === 0) {
              // No children yet — this becomes the main line (children[0])
              cloned.children = [optimisticNode];
            } else {
              // Parent already has children — new move is a variation
              cloned.children = [...(cloned.children || []), optimisticNode];
            }
          }
        }
        return cloned;
      };
      const optimisticTree = cloneAndInsert(curTree);

      // Update tree + selection IMMEDIATELY
      setCurrentTree(optimisticTree);
      setSelectedNodeId(tempId);
      setSelectedNode(optimisticNode);
      // Also update refs so next queued move sees this node as parent
      selectedNodeRef.current = optimisticNode;
      currentTreeRef.current = optimisticTree;

      // Resolve real parent ID (temp → real via map, with retry for in-flight saves)
      let realParentId = curSelectedNode.id;
      if (curSelectedNode.id.startsWith('temp-')) {
        let resolvedId = tempToRealIdRef.current.get(curSelectedNode.id);
        if (!resolvedId) {
          // Wait for the previous move's API call to resolve the temp ID
          for (let attempt = 0; attempt < 50; attempt++) {
            await new Promise(r => setTimeout(r, 100));
            resolvedId = tempToRealIdRef.current.get(curSelectedNode.id);
            if (resolvedId) break;
          }
        }
        if (resolvedId) {
          realParentId = resolvedId;
        } else {
          // Still unresolved after 5s — skip this move
          console.error('Could not resolve temp parent ID:', curSelectedNode.id);
          setBoardFen(curSelectedNode.fen);
          setSnackbar({ open: true, msg: 'Move failed — parent not saved yet', severity: 'error' });
          continue;
        }
      }

      try {
        const newNode = await addNode(realParentId, moveSan, moveUci, newFen);
        tempToRealIdRef.current.set(tempId, newNode.id);

        const realNode: OpeningNode = { ...newNode, children: [] };
        setCurrentTree(prev => {
          if (!prev) return prev;
          const replaceTempId = (node: OpeningNode): OpeningNode => {
            const cloned = { ...node, children: (node.children || []).map(replaceTempId) };
            if (cloned.id === tempId) {
              return { ...realNode, children: cloned.children };
            }
            return cloned;
          };
          const updated = replaceTempId(prev);
          currentTreeRef.current = updated;
          return updated;
        });
        setSelectedNodeId(newNode.id);
        setSelectedNode(realNode);
        selectedNodeRef.current = realNode;
        fetchTree(selectedRepertoireId, true).catch(() => {});
      } catch (e: any) {
        setBoardFen(curSelectedNode.fen);
        const revertId = curSelectedNode.id.startsWith('temp-')
          ? (tempToRealIdRef.current.get(curSelectedNode.id) || curSelectedNode.parent_id!)
          : curSelectedNode.id;
        setSelectedNodeId(revertId);
        fetchTree(selectedRepertoireId, true).catch(() => {});
        setSnackbar({ open: true, msg: e.message, severity: 'error' });
      }
    }

    isProcessingMoveRef.current = false;
  }, [selectedRepertoireId, addNode, fetchTree, setCurrentTree]);

  const handleBoardMove = useCallback(async (
    from: string, to: string, piece: string, newFen: string, moveSan: string, moveUci: string
  ) => {
    if (!selectedNodeRef.current || !selectedRepertoireId || !currentTreeRef.current) return;

    // Optimistic: update board FEN immediately so the piece stays in place
    setBoardFen(newFen);

    // Quick check for existing child (navigate instead of creating)
    const newFenParts = newFen.split(' ').slice(0, 4).join(' ');
    const fenMatch = (c: OpeningNode) => c.fen.split(' ').slice(0, 4).join(' ') === newFenParts;
    const curSelectedNode = selectedNodeRef.current;
    let existingChild = curSelectedNode.children?.find(fenMatch) || null;
    if (!existingChild && currentTreeRef.current) {
      const findInTree = (node: OpeningNode, id: string): OpeningNode | null => {
        if (node.id === id) return node;
        for (const ch of node.children || []) { const f = findInTree(ch, id); if (f) return f; }
        return null;
      };
      const treeParent = findInTree(currentTreeRef.current, curSelectedNode.id);
      existingChild = treeParent?.children?.find(fenMatch) || null;
    }

    if (existingChild) {
      setSelectedNodeId(existingChild.id);
      setSelectedNode(existingChild);
      setBoardFen(existingChild.fen);
      return;
    }

    // Queue the move data (NOT a closure) and process
    moveQueueRef.current.push({ from, to, piece, newFen, moveSan, moveUci });
    processQueue();
  }, [selectedRepertoireId, processQueue]);

  // Handle move tree click — navigate to the child node matching the clicked move
  const handleMoveTreeClick = useCallback((move: MoveCandidate) => {
    if (!selectedNode || !currentTree) return;
    // Look for existing child with matching UCI
    const child = selectedNode.children?.find(c => c.move_uci === move.uci);
    if (child) {
      handleNodeSelect(child);
      return;
    }
    // If no existing child, simulate a board move
    if (move.uci && move.uci.length >= 4) {
      const from = move.uci.substring(0, 2);
      const to = move.uci.substring(2, 4);
      import('chess.js').then(({ Chess }) => {
        const chess = new Chess(selectedNode.fen);
        const result = chess.move({ from, to, promotion: move.uci.length > 4 ? move.uci[4] : undefined });
        if (result) {
          handleBoardMove(from, to, '', chess.fen(), result.san, move.uci);
        }
      });
    }
  }, [selectedNode, currentTree, handleNodeSelect, handleBoardMove]);

  // Navigation handlers
  const handleReset = useCallback(() => {
    if (currentTree) {
      handleNodeSelect(currentTree);
    }
  }, [currentTree, handleNodeSelect]);

  const handleGoToStart = useCallback(() => {
    if (currentTree) {
      handleNodeSelect(currentTree);
    }
  }, [currentTree, handleNodeSelect]);

  const handlePrev = useCallback(() => {
    if (!selectedNode?.parent_id || !currentTree) return;
    const parent = findNode(currentTree, selectedNode.parent_id);
    if (parent) handleNodeSelect(parent);
  }, [selectedNode, currentTree, findNode, handleNodeSelect]);

  const handleNext = useCallback(() => {
    if (!selectedNode?.children?.length) return;
    handleNodeSelect(selectedNode.children[0]);
  }, [selectedNode, handleNodeSelect]);

  const handleGoToEnd = useCallback(() => {
    if (!selectedNode) return;
    const deepest = findDeepestMainLine(selectedNode);
    handleNodeSelect(deepest);
  }, [selectedNode, findDeepestMainLine, handleNodeSelect]);

  const handleFlip = useCallback(() => {
    setBoardOrientation(o => o === 'white' ? 'black' : 'white');
  }, []);

  // ─── Browse mode handlers ───
  const handleBrowseMoveClick = useCallback((san: string) => {
    import('chess.js').then(({ Chess }) => {
      const chess = new Chess(browseFen);
      const move = chess.move(san);
      if (move) {
        const newFen = chess.fen();
        setBrowseFen(newFen);
        setBrowseMoveHistory(prev => [...prev, { san, fen: newFen }]);
      }
    });
  }, [browseFen]);

  const handleBrowseReset = useCallback(() => {
    setBrowseFen(STARTING_FEN);
    setBrowseMoveHistory([]);
  }, []);

  const handleBrowsePrev = useCallback(() => {
    if (browseMoveHistory.length === 0) return;
    const newHistory = browseMoveHistory.slice(0, -1);
    setBrowseMoveHistory(newHistory);
    if (newHistory.length === 0) {
      setBrowseFen(STARTING_FEN);
    } else {
      setBrowseFen(newHistory[newHistory.length - 1].fen);
    }
  }, [browseMoveHistory]);

  const handleBrowseNext = useCallback(() => {
    // In browse mode, "next" doesn't make sense since we don't have a predetermined line
    // This could be implemented later if we track forward/backward through history
  }, []);

  const handleBrowseBoardMove = useCallback((
    from: string, to: string, piece: string, newFen: string, moveSan: string, moveUci: string
  ) => {
    setBrowseFen(newFen);
    setBrowseMoveHistory(prev => [...prev, { san: moveSan, fen: newFen }]);
  }, []);

  // CRUD handlers
  const handleCreateRepertoire = useCallback(async (name: string, color: 'w' | 'b') => {
    try {
      const rep = await createRepertoire(name, color);
      setSelectedRepertoireId(rep.id);
    } catch (e: any) {
      setSnackbar({ open: true, msg: e.message, severity: 'error' });
    }
  }, [createRepertoire]);

  const handleRenameRepertoire = useCallback(async (id: string, name: string) => {
    try {
      await updateRepertoire(id, { name } as any);
    } catch (e: any) {
      setSnackbar({ open: true, msg: e.message, severity: 'error' });
    }
  }, [updateRepertoire]);

  const handleDeleteRepertoire = useCallback(async (id: string) => {
    try {
      await deleteRepertoire(id);
      setSelectedRepertoireId(null);
      setSelectedNode(null);
      setBoardFen(STARTING_FEN);
    } catch (e: any) {
      setSnackbar({ open: true, msg: e.message, severity: 'error' });
    }
  }, [deleteRepertoire]);

  const handleUpdateNotes = useCallback(async (nodeId: string, notes: string) => {
    try {
      await updateNode(nodeId, { notes });
      if (selectedRepertoireId) await fetchTree(selectedRepertoireId);
    } catch (e: any) {
      setSnackbar({ open: true, msg: e.message, severity: 'error' });
    }
  }, [updateNode, selectedRepertoireId, fetchTree]);

  const handleToggleCritical = useCallback(async (nodeId: string, isCritical: boolean) => {
    try {
      await updateNode(nodeId, { isCritical });
      if (selectedRepertoireId) await fetchTree(selectedRepertoireId);
    } catch (e: any) {
      setSnackbar({ open: true, msg: e.message, severity: 'error' });
    }
  }, [updateNode, selectedRepertoireId, fetchTree]);

  const handleDeleteNode = useCallback(async (nodeId: string) => {
    try {
      // Navigate to parent before deleting
      const parentId = selectedNode?.parent_id || null;
      await deleteNode(nodeId);
      if (selectedRepertoireId) {
        setSelectedNodeId(parentId);
        await fetchTree(selectedRepertoireId);
      }
    } catch (e: any) {
      setSnackbar({ open: true, msg: e.message, severity: 'error' });
    }
  }, [deleteNode, selectedRepertoireId, fetchTree, selectedNode]);

  const handleDeleteLastMove = useCallback(async () => {
    if (!selectedNode || !selectedNode.move_san) return; // Can't delete root
    await handleDeleteNode(selectedNode.id);
  }, [selectedNode, handleDeleteNode]);

  const handleDeleteAllMoves = useCallback(async () => {
    if (!currentTree || !selectedRepertoireId) return;
    const rootChildren = currentTree.children || [];
    if (rootChildren.length === 0) return;
    if (!window.confirm('Delete all moves in this repertoire?')) return;
    try {
      for (const child of rootChildren) {
        await deleteNode(child.id);
      }
      setSelectedNodeId(null); // Will resolve to root
      await fetchTree(selectedRepertoireId);
    } catch (e: any) {
      setSnackbar({ open: true, msg: e.message, severity: 'error' });
    }
  }, [currentTree, selectedRepertoireId, deleteNode, fetchTree]);

  const handleImportPgn = useCallback(async (pgn: string, maxPly: number) => {
    if (!selectedRepertoireId) throw new Error('No repertoire selected');
    const result = await importPgn(selectedRepertoireId, pgn, maxPly);
    await fetchTree(selectedRepertoireId);
    return result;
  }, [selectedRepertoireId, importPgn, fetchTree]);

  const handleExportPgn = useCallback(async () => {
    if (!selectedRepertoireId) return;
    try {
      const pgn = await exportPgn(selectedRepertoireId);
      // Download as file
      const blob = new Blob([pgn], { type: 'application/x-chess-pgn' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      const rep = repertoires.find(r => r.id === selectedRepertoireId);
      a.download = `${rep?.name || 'repertoire'}.pgn`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e: any) {
      setSnackbar({ open: true, msg: e.message, severity: 'error' });
    }
  }, [selectedRepertoireId, exportPgn, repertoires]);

  const handleSearchGames = useCallback((fen: string) => {
    setGameSearchFen(fen);
    setGameSearchOpen(true);
  }, []);

  // ─── Game viewer handlers ───
  const handleOpenGame = useCallback(async (game: any) => {
    const gameId = String(game.id || `${game.white_name || game.white}-${game.black_name || game.black}-${game.date}`);
    const existing = openedGames.find(g => g.id === gameId);
    if (existing) {
      setActiveTab(gameId);
      return;
    }

    if (openedGames.length >= 10) {
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
      pgn: pgnText,
      moves: parsed.moves,
      fens: parsed.fens,
      startingFen: parsed.startingFen,
      source: game.user_id ? 'user' : (game.source || 'twic'),
    };

    setOpenedGames(prev => [...prev, newGame]);
    setGameMoveIndices(prev => ({ ...prev, [gameId]: -1 }));
    setActiveTab(gameId);

    // Track favorite state for user games
    if (game.is_favorite) {
      setFavoriteGameIds(prev => new Set(prev).add(gameId));
    }
  }, [openedGames, setSnackbar, fetchGamePgn]);

  const handleCloseGame = useCallback((gameId: string, e?: React.MouseEvent) => {
    if (e) e.stopPropagation();
    setOpenedGames(prev => prev.filter(g => g.id !== gameId));
    setGameMoveIndices(prev => {
      const next = { ...prev };
      delete next[gameId];
      return next;
    });
    if (activeTab === gameId) setActiveTab(lastHomeTabRef.current);
  }, [activeTab]);

  const handleGameMoveChange = useCallback((gameId: string, moveIndex: number) => {
    setGameMoveIndices(prev => ({ ...prev, [gameId]: moveIndex }));
  }, []);

  const activeGame = openedGames.find(g => g.id === activeTab);
  const activeGameFen = activeGame
    ? (gameMoveIndices[activeGame.id] ?? -1) === -1
      ? activeGame.startingFen
      : activeGame.fens[gameMoveIndices[activeGame.id]] || activeGame.startingFen
    : null;

  const handleLinkGame = useCallback(async (game: GameSearchResult) => {
    if (!selectedNode) return;
    try {
      await linkGame(selectedNode.id, {
        game_source: game.source as any,
        game_id: String(game.id),
        game_pgn: game.pgn || null,
        white_player: game.white,
        black_player: game.black,
        white_elo: game.white_elo,
        black_elo: game.black_elo,
        result: game.result,
        date_played: game.date,
        event_name: game.event || null,
      } as any);
      // Refresh game links
      const links = await getNodeGames(selectedNode.id);
      setGameLinks(links);
      setSnackbar({ open: true, msg: t('gameLinked'), severity: 'success' });
    } catch (e: any) {
      setSnackbar({ open: true, msg: e.message, severity: 'error' });
    }
  }, [selectedNode, linkGame, getNodeGames]);

  // ─── Arrow annotations for the board ───
  const boardArrows = useMemo(() => {
    if (!selectedNode?.arrows?.length) return [];
    return selectedNode.arrows.map(a => ({
      from: a.from_square as Key,
      to: a.to_square as Key,
      brush: a.color || 'green'
    }));
  }, [selectedNode?.arrows]);

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

  const selectedRep = repertoires.find(r => r.id === selectedRepertoireId);

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

      {/* Mode switcher + Tab bar */}
      <Box sx={{ px: { xs: 1, sm: 2 }, pt: { xs: 1, sm: 2 }, pb: 0 }}>
        {/* Mode tabs hidden — Browse Database disabled for now */}

        {/* Game tabs — only show in repertoire mode */}
        {mode === 'repertoire' && (
          <Box sx={{ display: 'flex', gap: 0.5, overflowX: 'auto', pb: 0.5, '&::-webkit-scrollbar': { height: 3 }, '&::-webkit-scrollbar-thumb': { bgcolor: 'var(--text-tertiary)', borderRadius: 2 } }}>
            <Chip
              label={t('debutTab')}
              onClick={() => setActiveTab('debut')}
              sx={{
                height: 28, fontSize: 12, fontWeight: 600,
                borderRadius: '9999px',
                bgcolor: activeTab === 'debut' ? 'primary.main' : 'rgba(255,255,255,0.95)',
                color: activeTab === 'debut' ? '#fff' : 'var(--text-secondary)',
                border: activeTab === 'debut' ? 'none' : '1px solid rgba(31,41,55,0.1)',
                '&:hover': { bgcolor: activeTab === 'debut' ? 'primary.dark' : 'var(--surface-card-hover)' },
                cursor: 'pointer', flexShrink: 0,
              }}
            />
            <Chip
              icon={<FolderOpen sx={{ fontSize: 14 }} />}
              label={t('myGamesTab')}
              onClick={() => setActiveTab('my-games')}
              sx={{
                height: 28, fontSize: 12, fontWeight: 600,
                borderRadius: '9999px',
                bgcolor: activeTab === 'my-games' ? 'primary.main' : 'rgba(255,255,255,0.95)',
                color: activeTab === 'my-games' ? '#fff' : 'var(--text-secondary)',
                border: activeTab === 'my-games' ? 'none' : '1px solid rgba(31,41,55,0.1)',
                '&:hover': { bgcolor: activeTab === 'my-games' ? 'primary.dark' : 'var(--surface-card-hover)' },
                '& .MuiChip-icon': { color: activeTab === 'my-games' ? '#fff' : 'var(--text-secondary)' },
                cursor: 'pointer', flexShrink: 0,
              }}
            />
          {openedGames.map(g => (
            <Chip
              key={g.id}
              label={`♟ ${g.white.split(',')[0]} vs ${g.black.split(',')[0]}`}
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
      {mode === 'browse' ? (
        // ─── Browse Database Mode ───
        <Box sx={{
          display: 'flex',
          flexDirection: { xs: 'column', lg: 'row' },
          flex: { xs: 'none', lg: 1 },
          p: { xs: 0, sm: 1, lg: 2 },
          gap: { xs: 1, lg: 2 },
          pb: { xs: 0, md: 2 },
        }}>
          {/* Left: Board + Move History */}
          <Box sx={{
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            flexShrink: 0,
          }}>
            <DebutBoard
              fen={browseFen}
              orientation={boardOrientation}
              onMove={handleBrowseBoardMove}
              customArrows={[]}
              onReset={handleBrowseReset}
              onGoToStart={handleBrowseReset}
              onPrev={handleBrowsePrev}
              onNext={handleBrowseNext}
              onGoToEnd={() => {}}
              onFlip={handleFlip}
            />

            {/* Move history breadcrumb */}
            <Box sx={{
              width: { xs: 'calc(100% - 32px)', sm: 'calc(100% - 24px)', lg: 520 },
              maxWidth: 520,
              mt: 0.5,
              p: 1.5,
              bgcolor: 'var(--surface-card)',
              borderRadius: '16px',
              border: '1px solid var(--border-strong)',
              minHeight: 48,
            }}>
              <Typography variant="caption" sx={{ color: 'var(--text-tertiary)', fontWeight: 600, mb: 0.5, display: 'block' }}>
                {t('browseMode.moveHistory')}
              </Typography>
              <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5 }}>
                {browseMoveHistory.length === 0 ? (
                  <Typography variant="body2" sx={{ color: 'var(--text-tertiary)', fontStyle: 'italic' }}>
                    {t('startingPosition')}
                  </Typography>
                ) : (
                  browseMoveHistory.map((move, idx) => (
                    <Chip
                      key={idx}
                      label={`${Math.floor(idx / 2) + 1}${idx % 2 === 0 ? '.' : '...'} ${move.san}`}
                      size="small"
                      sx={{
                        height: 24,
                        fontSize: 12,
                        bgcolor: 'rgba(0,0,0,0.05)',
                        fontFamily: 'monospace',
                        '&:hover': { bgcolor: 'rgba(0,0,0,0.1)' },
                      }}
                    />
                  ))
                )}
              </Box>
            </Box>
          </Box>

          {/* Right: TwicExplorer */}
          <Box sx={{
            flex: { xs: 'none', lg: 1 },
            display: 'flex',
            flexDirection: 'column',
            bgcolor: { xs: 'transparent', lg: 'var(--surface-card)' },
            borderRadius: { xs: 0, lg: '24px' },
            border: { xs: 'none', lg: '1px solid rgba(31,41,55,0.1)' },
            overflow: { xs: 'visible', lg: 'auto' },
            minWidth: 0,
            maxHeight: { lg: 'calc(100vh - 32px)' },
            p: { xs: 1, lg: 2 },
          }}>
            <TwicExplorer fen={browseFen} onMoveClick={handleBrowseMoveClick} />
          </Box>
        </Box>
      ) : (
        // ─── Repertoire Mode ───
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
          }}>
            {/* Board + Eval bar row */}
            <Box sx={{ display: 'flex', flexDirection: 'row', alignItems: 'flex-start', gap: 0.5 }}>
              {stockfishEnabled && activeTab === 'debut' && (
                <ReplayEvalBar
                  evaluation={evaluation?.lines?.[0] ? { cp: evaluation.lines[0].cp, mate: evaluation.lines[0].mate } : null}
                  isAnalyzing={isAnalyzing}
                  depth={depth}
                  orientation={boardOrientation}
                  height={boardSize}
                />
              )}
            <DebutBoard
              fen={activeTab === 'my-games' && !activeGame ? myGamesFen : (editTreeFen || activeGameFen || boardFen)}
              orientation={boardOrientation}
              onMove={activeTab === 'debut' ? handleBoardMove : (isActiveGameEditable ? handleGameBoardMove : (activeTab === 'my-games' && !activeGame ? handleMyGamesBoardMove : (() => {})))}
              customArrows={boardArrows}
              onReset={activeTab === 'debut' ? handleReset : (isActiveGameEditable ? handleEditTreeGoToStart : (activeTab === 'my-games' && !activeGame ? handleMyGamesReset : () => activeGame && handleGameMoveChange(activeGame.id, -1)))}
              onGoToStart={activeTab === 'debut' ? handleGoToStart : (isActiveGameEditable ? handleEditTreeGoToStart : (activeTab === 'my-games' && !activeGame ? handleMyGamesReset : () => activeGame && handleGameMoveChange(activeGame.id, -1)))}
              onPrev={activeTab === 'debut' ? handlePrev : (isActiveGameEditable ? handleEditTreePrev : (activeTab === 'my-games' && !activeGame ? handleMyGamesPrev : () => activeGame && handleGameMoveChange(activeGame.id, Math.max(-1, (gameMoveIndices[activeGame.id] ?? -1) - 1))))}
              onNext={activeTab === 'debut' ? handleNext : (isActiveGameEditable ? handleEditTreeNext : (activeTab === 'my-games' && !activeGame ? handleMyGamesNext : () => activeGame && handleGameMoveChange(activeGame.id, Math.min((activeGame?.moves.length ?? 1) - 1, (gameMoveIndices[activeGame.id] ?? -1) + 1))))}
              onGoToEnd={activeTab === 'debut' ? handleGoToEnd : (isActiveGameEditable ? handleEditTreeGoToEnd : (activeTab === 'my-games' && !activeGame ? handleMyGamesGoToEnd : () => activeGame && handleGameMoveChange(activeGame.id, (activeGame?.moves.length ?? 1) - 1)))}
              onFlip={handleFlip}
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
                onUndo={() => {
                  setMyGamesSanMoves(prev => prev.slice(0, -1));
                  setMyGamesMoveHistory(prev => prev.slice(0, -1));
                  setMyGamesMoveIndex(prev => Math.max(0, prev - 1));
                  setMyGamesComments(prev => {
                    const next = { ...prev };
                    delete next[myGamesSanMoves.length];
                    return next;
                  });
                }}
                onReset={handleMyGamesReset}
              />
            )}

            {/* Stockfish toggle + engine lines — only in Debut tab */}
            {activeTab === 'debut' && (
              <Box sx={{
                width: { xs: 'calc(100% - 32px)', sm: 'calc(100% - 24px)', lg: 520 },
                maxWidth: 520,
                mx: 'auto',
                mt: 0.5,
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
                    Stockfish 16
                  </Typography>
                  {stockfishEnabled && depth > 0 && (
                    <Typography variant="caption" sx={{ color: 'var(--text-tertiary)', fontFamily: 'monospace', fontSize: 11 }}>
                      d{depth}
                    </Typography>
                  )}
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

                {/* Best line display */}
                {stockfishEnabled && bestLine && bestLine.sanMoves.length > 0 && (
                  <Box sx={{
                    mt: 0.5, px: 1.5, py: 1,
                    bgcolor: 'rgba(0,0,0,0.03)',
                    borderRadius: '10px',
                    display: 'flex', alignItems: 'center', gap: 1,
                    fontFamily: 'monospace',
                  }}>
                    <Typography component="span" sx={{
                      fontWeight: 700, fontSize: 14, fontFamily: 'monospace',
                      color: bestLine.evalText.startsWith('+') ? '#16a34a' : bestLine.evalText.startsWith('-') ? '#dc2626' : 'var(--text-primary)',
                    }}>
                      {bestLine.evalText}
                    </Typography>
                    <Typography component="span" sx={{
                      fontSize: 13, fontFamily: 'monospace', color: 'var(--text-secondary)',
                      overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                    }}>
                      {bestLine.sanMoves.join(' ')}
                    </Typography>
                  </Box>
                )}

                {/* Engine lines */}
                {stockfishEnabled && evaluation?.lines && evaluation.lines.length > 0 && (
                  <Box sx={{ mt: 0.5 }}>
                    <ReplayEngineLines
                      lines={evaluation.lines}
                      isAnalyzing={isAnalyzing}
                      currentFen={boardFen}
                      depth={depth}
                    />
                  </Box>
                )}
              </Box>
            )}

            {/* Move notation — only show in Debut tab */}
            {activeTab === 'debut' && (
              <Box sx={{
                width: { xs: 'calc(100% - 32px)', sm: 'calc(100% - 24px)', lg: 520 },
                maxWidth: 520,
                maxHeight: { xs: 88, lg: 240 },
                mx: 'auto',
                mt: 0.5,
                overflow: 'auto',
                bgcolor: 'var(--surface-card)',
                borderRadius: '24px',
                border: '1px solid var(--border-strong)',
                '&::-webkit-scrollbar': { width: '6px' },
                '&::-webkit-scrollbar-track': { background: 'var(--surface-page)', borderRadius: '3px' },
                '&::-webkit-scrollbar-thumb': { background: 'var(--text-tertiary)', borderRadius: '3px', '&:hover': { background: 'var(--text-secondary)' } },
              }}>
                <MoveNotation
                  tree={currentTree}
                  selectedNodeId={selectedNode?.id || null}
                  onNodeSelect={handleNodeSelect}
                  onDeleteLast={handleDeleteLastMove}
                  onDeleteAll={handleDeleteAllMoves}
                  loading={treeLoading}
                />
              </Box>
            )}

            {/* Game viewer notation — below board on small screens only */}
            {activeTab !== 'debut' && activeGame && (
              <Box sx={{
                display: { xs: 'block', lg: 'none' },
                width: '100%',
                maxWidth: { xs: '100%' },
                maxHeight: { xs: 150 },
                overflow: 'auto',
              }}>
                <GameViewerPanel
                  game={activeGame}
                  currentMoveIndex={gameMoveIndices[activeGame.id] ?? -1}
                  onMoveIndexChange={(idx) => handleGameMoveChange(activeGame.id, idx)}
                  onSaveToMyGames={handleSaveToMyGames}
                  isSaved={savedGameIds.has(activeGame.id)}
                  onEditGame={activeGame.source === 'user' ? () => handleEditGameFromViewer(activeGame) : undefined}
                  onToggleFavorite={activeGame.source === 'user' ? handleViewerToggleFavorite : undefined}
                  onDeleteGame={activeGame.source === 'user' ? handleViewerDeleteGame : undefined}
                  isFavorite={favoriteGameIds.has(activeGame.id)}
                  isEditable={isActiveGameEditable}
                  editTree={isActiveGameEditable ? gameMoveTree.tree : undefined}
                  editSelectedNodeId={isActiveGameEditable ? editTreeSelectedNodeId : undefined}
                  onEditNodeSelect={isActiveGameEditable ? handleEditNodeSelect : undefined}
                  onEditSave={isActiveGameEditable ? handleEditTreeSave : undefined}
                  editIsDirty={isActiveGameEditable ? gameMoveTree.isDirty : undefined}
                  editContextMenuActions={editContextMenuActions}
                  onTreePrev={isActiveGameEditable ? handleEditTreePrev : undefined}
                  onTreeNext={isActiveGameEditable ? handleEditTreeNext : undefined}
                  onTreeGoToStart={isActiveGameEditable ? handleEditTreeGoToStart : undefined}
                  onTreeGoToEnd={isActiveGameEditable ? handleEditTreeGoToEnd : undefined}
                />
              </Box>
            )}
          </Box>

          {/* Right: Repertoire + Details */}
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
              <>
                <RepertoireSelector
                  repertoires={repertoires}
                  selectedId={selectedRepertoireId}
                  onSelect={setSelectedRepertoireId}
                  onCreate={handleCreateRepertoire}
                  onRename={handleRenameRepertoire}
                  onDelete={handleDeleteRepertoire}
                  onImportPgn={() => setPgnImporterOpen(true)}
                  onExportPgn={handleExportPgn}
                  loading={loading}
                />
                <Box sx={{ flex: 1, overflow: 'auto' }}>
                  {/* Move Tree (ChessBase-style) */}
                  <MoveTree
                    moves={displayedMoves}
                    totalGames={displayedTotalGames}
                    loading={displayedLoading}
                    onMoveClick={handleMoveTreeClick}
                    fen={selectedNode?.fen}
                    source={moveTreeSource}
                    onSourceChange={setMoveTreeSource}
                  />

                  {/* Position Summary (ECO + aggregate W/D/L) */}
                  <PositionSummary
                    ecoCode={selectedNode?.eco_code || null}
                    openingName={selectedNode?.opening_name || null}
                    totalGames={candidatesTotalGames}
                    moves={candidateMoves}
                  />


                  {/* Master Games + Linked Games */}
                  <NodeDetailsPanel
                    node={selectedNode}
                    onUpdateNotes={handleUpdateNotes}
                    onToggleCritical={handleToggleCritical}
                    onDeleteNode={handleDeleteNode}
                    onSearchGames={handleSearchGames}
                    gameLinks={gameLinks}
                    gameLinksLoading={gameLinksLoading}
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
              </>
            ) : activeTab === 'my-games' ? (
              <Box sx={{ flex: 1, overflow: 'auto' }}>
                <MyGamesPanel
                  onOpenGame={handleOpenGame}
                  boardPgn={buildMyGamesPgn()}
                  boardHasMoves={myGamesSanMoves.length > 0}
                  onBoardReset={handleMyGamesReset}
                />
              </Box>
            ) : activeGame ? (
              <Box sx={{ display: { xs: 'none', lg: 'flex' }, flex: 1, flexDirection: 'column', overflow: 'auto' }}>
                <GameViewerPanel
                  game={activeGame}
                  currentMoveIndex={gameMoveIndices[activeGame.id] ?? -1}
                  onMoveIndexChange={(idx) => handleGameMoveChange(activeGame.id, idx)}
                  onSaveToMyGames={handleSaveToMyGames}
                  isSaved={savedGameIds.has(activeGame.id)}
                  onEditGame={activeGame.source === 'user' ? () => handleEditGameFromViewer(activeGame) : undefined}
                  onToggleFavorite={activeGame.source === 'user' ? handleViewerToggleFavorite : undefined}
                  onDeleteGame={activeGame.source === 'user' ? handleViewerDeleteGame : undefined}
                  isFavorite={favoriteGameIds.has(activeGame.id)}
                  isEditable={isActiveGameEditable}
                  editTree={isActiveGameEditable ? gameMoveTree.tree : undefined}
                  editSelectedNodeId={isActiveGameEditable ? editTreeSelectedNodeId : undefined}
                  onEditNodeSelect={isActiveGameEditable ? handleEditNodeSelect : undefined}
                  onEditSave={isActiveGameEditable ? handleEditTreeSave : undefined}
                  editIsDirty={isActiveGameEditable ? gameMoveTree.isDirty : undefined}
                  editContextMenuActions={editContextMenuActions}
                />
              </Box>
            ) : null}
          </Box>
        </Box>
      )}

      {/* Modals */}
      <PgnImporter
        open={pgnImporterOpen}
        onClose={() => setPgnImporterOpen(false)}
        onImport={handleImportPgn}
        repertoireName={selectedRep?.name || ''}
      />

      <GameSearchPanel
        fen={gameSearchFen}
        onLinkGame={handleLinkGame}
        open={gameSearchOpen}
        onClose={() => setGameSearchOpen(false)}
        onSearch={searchGamesStream}
        fetchGamePgn={fetchGamePgn}
      />

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
