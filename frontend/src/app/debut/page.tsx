'use client';

import { useState, useEffect, useCallback, useMemo } from 'react';
import { useTranslations } from 'next-intl';
import { Box, Typography, Snackbar, Alert, Chip } from '@mui/material';
import { useBackendHealth } from '@/hooks/useBackendHealth';
import dynamic from 'next/dynamic';
import { useOpeningRepertoire } from '@/hooks/useOpeningRepertoire';
import type { OpeningNode, GameSearchResult, GameLink } from '@/hooks/useOpeningRepertoire';
import type { Arrow } from 'react-chessboard/dist/chessboard/types';

// Dynamic imports to avoid SSR issues
const DebutBoard = dynamic(() => import('@/components/openings/DebutBoard'), {
  ssr: false,
  loading: () => <div className="animate-pulse h-80 bg-gray-200 rounded-xl" />
});
const RepertoireSelector = dynamic(() => import('@/components/openings/RepertoireSelector'), {
  ssr: false,
  loading: () => <div className="animate-pulse h-16 bg-gray-200 rounded-xl" />
});
const MoveNotation = dynamic(() => import('@/components/openings/MoveNotation'), {
  ssr: false,
  loading: () => <div className="animate-pulse h-20 bg-gray-200 rounded-xl" />
});
const NodeDetailsPanel = dynamic(() => import('@/components/openings/NodeDetailsPanel'), {
  ssr: false,
  loading: () => <div className="animate-pulse h-60 bg-gray-200 rounded-xl" />
});
const PgnImporter = dynamic(() => import('@/components/openings/PgnImporter'), {
  ssr: false,
  loading: () => null
});
const GameSearchPanel = dynamic(() => import('@/components/openings/GameSearchPanel'), {
  ssr: false,
  loading: () => null
});

import GameViewerPanel, { OpenedGame, parseGamePgn } from '@/components/openings/GameViewerPanel';
import { Close } from '@mui/icons-material';

const STARTING_FEN = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1';

export default function DebutPage() {
  const t = useTranslations('debut');
  // Auth disabled
  const session = { isLoaded: true, isSignedIn: true };
  const backendHealthy = useBackendHealth();

  const [mounted, setMounted] = useState(false);
  useEffect(() => { setMounted(true); }, []);

  // ─── Core state ───
  const [selectedRepertoireId, setSelectedRepertoireId] = useState<string | null>(null);
  const [selectedNode, setSelectedNode] = useState<OpeningNode | null>(null);
  const [boardFen, setBoardFen] = useState(STARTING_FEN);
  const [boardOrientation, setBoardOrientation] = useState<'white' | 'black'>('white');

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
  const [masterGamesFilters, setMasterGamesFilters] = useState({ playerName: '', playerColor: '', sortBy: 'rating' });

  // ─── Game viewer tabs ───
  const [openedGames, setOpenedGames] = useState<OpenedGame[]>([]);
  const [activeTab, setActiveTab] = useState<string>('debut');
  const [gameMoveIndices, setGameMoveIndices] = useState<Record<string, number>>({});

  // ─── Snackbar ───
  const [snackbar, setSnackbar] = useState<{ open: boolean; msg: string; severity: 'success' | 'error' }>({ open: false, msg: '', severity: 'success' });

  // ─── Hook ───
  const {
    repertoires, loading, error, fetchRepertoires,
    createRepertoire, updateRepertoire, deleteRepertoire,
    currentTree, setCurrentTree, treeLoading, fetchTree,
    addNode, updateNode, deleteNode,
    importPgn, exportPgn,
    addArrow, deleteArrow,
    fetchGamesByPosition, fetchPositionCount, fetchGamePgn,
    searchGamesStream, linkGame, getNodeGames, deleteGameLink,
  } = useOpeningRepertoire();

  // ─── Fetch repertoires on mount ───
  useEffect(() => { fetchRepertoires(); }, [fetchRepertoires]);

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
    if (selectedNode && selectedNode.move_san !== null) {
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
      masterGamesFilters.sortBy
    )
      .then((data) => {
        if (!cancelled) {
          setMasterGames(data.games);
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
  }, [selectedNode?.fen, masterGamesFilters, fetchGamesByPosition, fetchPositionCount]);

  // ─── Handlers ───

  const handleNodeSelect = useCallback((node: OpeningNode) => {
    setSelectedNodeId(node.id);
    setSelectedNode(node);
    setBoardFen(node.fen);
    setMasterGamesFilters({ playerName: '', playerColor: '', sortBy: 'rating' });
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

  const handleBoardMove = useCallback(async (
    from: string, to: string, piece: string, newFen: string, moveSan: string, moveUci: string
  ) => {
    if (!selectedNode || !selectedRepertoireId || !currentTree) return;

    // Optimistic: update board FEN immediately so the piece stays in place
    setBoardFen(newFen);

    // Check if child with this FEN already exists — search both selectedNode
    // AND currentTree (selectedNode may be optimistic with empty children)
    const newFenParts = newFen.split(' ').slice(0, 4).join(' ');
    const fenMatch = (c: OpeningNode) => c.fen.split(' ').slice(0, 4).join(' ') === newFenParts;

    let existingChild = selectedNode.children?.find(fenMatch) || null;
    if (!existingChild && currentTree) {
      // Deep search: find selectedNode in currentTree and check ITS children
      const findNode = (node: OpeningNode, id: string): OpeningNode | null => {
        if (node.id === id) return node;
        for (const ch of node.children || []) { const f = findNode(ch, id); if (f) return f; }
        return null;
      };
      const treeParent = findNode(currentTree, selectedNode.id);
      existingChild = treeParent?.children?.find(fenMatch) || null;
    }

    if (existingChild) {
      setSelectedNodeId(existingChild.id);
      setSelectedNode(existingChild);
      return;
    }

    // ── Optimistic tree update: notation appears INSTANTLY ──
    // Parse move number from FEN (fullmove counter is last field)
    const fenParts = newFen.split(' ');
    const isWhiteMove = fenParts[1] === 'b'; // if it's black's turn now, white just moved
    const moveNumber = parseInt(fenParts[5]) - (isWhiteMove ? 0 : 1);
    const tempId = `temp-${Date.now()}`;

    const optimisticNode: OpeningNode = {
      id: tempId,
      repertoire_id: selectedRepertoireId,
      parent_id: selectedNode.id,
      fen: newFen,
      move_san: moveSan,
      move_uci: moveUci,
      move_number: moveNumber || 1,
      is_white_move: isWhiteMove,
      opening_name: null,
      eco_code: null,
      notes: null,
      priority: 0,
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

    // Clone tree and splice in the new node (skip if FEN already exists)
    const cloneAndInsert = (node: OpeningNode): OpeningNode => {
      const cloned = { ...node, children: (node.children || []).map(cloneAndInsert) };
      if (node.id === selectedNode.id) {
        const alreadyHasFen = (cloned.children || []).some(fenMatch);
        if (!alreadyHasFen) {
          cloned.children = [...(cloned.children || []), optimisticNode];
        }
      }
      return cloned;
    };
    const optimisticTree = cloneAndInsert(currentTree);

    // Update tree + selection IMMEDIATELY — notation renders instantly
    setCurrentTree(optimisticTree);
    setSelectedNodeId(tempId);
    setSelectedNode(optimisticNode);

    // ── Background: persist to DB and reconcile ──
    // Use the REAL parent ID (not temp) — if selectedNode was temp, use its parent_id
    const realParentId = selectedNode.id.startsWith('temp-') ? selectedNode.parent_id! : selectedNode.id;

    try {
      const newNode = await addNode(realParentId, moveSan, moveUci, newFen);
      // Replace temp ID with real ID in tree and selection
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
        return replaceTempId(prev);
      });
      setSelectedNodeId(newNode.id);
      setSelectedNode(realNode);
      // Silently refresh tree in background (no loading spinner)
      fetchTree(selectedRepertoireId, true).catch(() => {});
    } catch (e: any) {
      // Revert optimistic update on error
      setBoardFen(selectedNode.fen);
      setSelectedNodeId(selectedNode.id.startsWith('temp-') ? selectedNode.parent_id! : selectedNode.id);
      fetchTree(selectedRepertoireId, true).catch(() => {});
      setSnackbar({ open: true, msg: e.message, severity: 'error' });
    }
  }, [selectedNode, selectedRepertoireId, currentTree, addNode, fetchTree, setCurrentTree]);

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
    };

    setOpenedGames(prev => [...prev, newGame]);
    setGameMoveIndices(prev => ({ ...prev, [gameId]: -1 }));
    setActiveTab(gameId);
  }, [openedGames, setSnackbar, fetchGamePgn]);

  const handleCloseGame = useCallback((gameId: string, e?: React.MouseEvent) => {
    if (e) e.stopPropagation();
    setOpenedGames(prev => prev.filter(g => g.id !== gameId));
    setGameMoveIndices(prev => {
      const next = { ...prev };
      delete next[gameId];
      return next;
    });
    if (activeTab === gameId) setActiveTab('debut');
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
  const boardArrows: Arrow[] = useMemo(() => {
    if (!selectedNode?.arrows?.length) return [];
    return selectedNode.arrows.map(a => [a.from_square, a.to_square, a.color || 'green'] as Arrow);
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

  if (!mounted) {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: '100vh', bgcolor: 'var(--surface-page)' }}>
        <Typography sx={{ color: 'var(--text-tertiary)' }}>Loading...</Typography>
      </Box>
    );
  }

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

      {/* Tab bar — always visible */}
      <Box sx={{ px: { xs: 1, sm: 2 }, pt: { xs: 1, sm: 2 }, pb: 0 }}>
        <Box sx={{ display: 'flex', gap: 0.5, overflowX: 'auto', pb: 0.5, '&::-webkit-scrollbar': { height: 3 }, '&::-webkit-scrollbar-thumb': { bgcolor: 'var(--text-tertiary)', borderRadius: 2 } }}>
          <Chip
            label={t('debutTab')}
            onClick={() => setActiveTab('debut')}
            sx={{
              height: 28, fontSize: 12, fontWeight: 600,
              bgcolor: activeTab === 'debut' ? 'primary.main' : 'var(--surface-card)',
              color: activeTab === 'debut' ? '#fff' : 'var(--text-secondary)',
              '&:hover': { bgcolor: activeTab === 'debut' ? 'primary.dark' : 'var(--surface-card-hover)' },
              cursor: 'pointer', flexShrink: 0,
            }}
          />
          {openedGames.map(g => (
            <Chip
              key={g.id}
              label={`♟ ${g.white.split(',')[0]} vs ${g.black.split(',')[0]}`}
              onClick={() => setActiveTab(g.id)}
              onDelete={() => handleCloseGame(g.id)}
              deleteIcon={<Close sx={{ fontSize: 14, color: 'var(--text-tertiary)', '&:hover': { color: 'var(--text-primary)' } }} />}
              sx={{
                height: 28, fontSize: 11, maxWidth: 200,
                bgcolor: activeTab === g.id ? 'primary.main' : 'var(--surface-card)',
                color: activeTab === g.id ? '#fff' : 'var(--text-secondary)',
                '&:hover': { bgcolor: activeTab === g.id ? 'primary.dark' : 'var(--surface-card-hover)' },
                cursor: 'pointer', flexShrink: 0,
                '& .MuiChip-label': { overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' },
              }}
            />
          ))}
        </Box>
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
        }}>
          <DebutBoard
            fen={activeGameFen || boardFen}
            orientation={boardOrientation}
            onMove={activeTab === 'debut' ? handleBoardMove : (() => {})}
            customArrows={boardArrows}
            onReset={activeTab === 'debut' ? handleReset : () => activeGame && handleGameMoveChange(activeGame.id, -1)}
            onGoToStart={activeTab === 'debut' ? handleGoToStart : () => activeGame && handleGameMoveChange(activeGame.id, -1)}
            onPrev={activeTab === 'debut' ? handlePrev : () => activeGame && handleGameMoveChange(activeGame.id, Math.max(-1, (gameMoveIndices[activeGame.id] ?? -1) - 1))}
            onNext={activeTab === 'debut' ? handleNext : () => activeGame && handleGameMoveChange(activeGame.id, Math.min((activeGame?.moves.length ?? 1) - 1, (gameMoveIndices[activeGame.id] ?? -1) + 1))}
            onGoToEnd={activeTab === 'debut' ? handleGoToEnd : () => activeGame && handleGameMoveChange(activeGame.id, (activeGame?.moves.length ?? 1) - 1)}
            onFlip={handleFlip}
          />

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
              borderRadius: 1,
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

          {/* Game viewer notation — when viewing a game tab */}
          {activeTab !== 'debut' && activeGame && (
            <Box sx={{
              width: '100%',
              maxWidth: { xs: '100%', lg: 520 },
              maxHeight: { xs: 150, lg: 280 },
              overflow: 'auto',
            }}>
              <GameViewerPanel
                game={activeGame}
                currentMoveIndex={gameMoveIndices[activeGame.id] ?? -1}
                onMoveIndexChange={(idx) => handleGameMoveChange(activeGame.id, idx)}
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
          borderRadius: { xs: 0, lg: 1 },
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
                />
              </Box>
            </>
          ) : activeGame ? (
            <Box sx={{ p: 2, color: 'var(--text-tertiary)' }}>
              <Typography variant="body2" sx={{ color: 'var(--text-secondary)' }}>
                Viewing game: {activeGame.white} vs {activeGame.black}
              </Typography>
            </Box>
          ) : null}
        </Box>
      </Box>

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
