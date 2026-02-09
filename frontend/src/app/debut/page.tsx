'use client';

import { useState, useEffect, useCallback, useMemo } from 'react';
import { Box, Typography, Snackbar, Alert } from '@mui/material';
import dynamic from 'next/dynamic';
import { useOpeningRepertoire } from '@/hooks/useOpeningRepertoire';
import type { OpeningNode, GameSearchResult, GameLink } from '@/hooks/useOpeningRepertoire';
import type { Arrow } from 'react-chessboard/dist/chessboard/types';

// Dynamic imports to avoid SSR issues
const DebutBoard = dynamic(() => import('@/components/openings/DebutBoard'), { ssr: false });
const RepertoireSelector = dynamic(() => import('@/components/openings/RepertoireSelector'), { ssr: false });
const OpeningTree = dynamic(() => import('@/components/openings/OpeningTree'), { ssr: false });
const NodeDetailsPanel = dynamic(() => import('@/components/openings/NodeDetailsPanel'), { ssr: false });
const PgnImporter = dynamic(() => import('@/components/openings/PgnImporter'), { ssr: false });
const GameSearchPanel = dynamic(() => import('@/components/openings/GameSearchPanel'), { ssr: false });

const STARTING_FEN = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1';

export default function DebutPage() {
  // Auth disabled
  const session = { isLoaded: true, isSignedIn: true };

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

  // ─── Snackbar ───
  const [snackbar, setSnackbar] = useState<{ open: boolean; msg: string; severity: 'success' | 'error' }>({ open: false, msg: '', severity: 'success' });

  // ─── Hook ───
  const {
    repertoires, loading, error, fetchRepertoires,
    createRepertoire, updateRepertoire, deleteRepertoire,
    currentTree, treeLoading, fetchTree,
    addNode, updateNode, deleteNode,
    importPgn, exportPgn,
    addArrow, deleteArrow,
    fetchGamesByPosition,
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

  // ─── Fetch tree when repertoire changes ───
  useEffect(() => {
    if (selectedRepertoireId) {
      fetchTree(selectedRepertoireId);
      const rep = repertoires.find(r => r.id === selectedRepertoireId);
      if (rep) {
        setBoardOrientation(rep.color === 'b' ? 'black' : 'white');
        setBoardFen(rep.starting_fen || STARTING_FEN);
        setSelectedNode(null);
      }
    }
  }, [selectedRepertoireId, fetchTree, repertoires]);

  // ─── Select root when tree loads (only if no node is selected) ───
  useEffect(() => {
    if (currentTree && !selectedNode) {
      setSelectedNode(currentTree);
      setBoardFen(currentTree.fen);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentTree?.id]);

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

  // ─── Auto-fetch master games when node changes ───
  useEffect(() => {
    if (!selectedNode) {
      setMasterGames([]);
      setMasterGamesTotal(0);
      return;
    }

    let cancelled = false;
    setMasterGamesLoading(true);

    fetchGamesByPosition(selectedNode.fen, 5)
      .then((data) => {
        if (!cancelled) {
          setMasterGames(data.games);
          setMasterGamesTotal(data.total);
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
  }, [selectedNode?.fen, fetchGamesByPosition]);

  // ─── Handlers ───

  const handleNodeSelect = useCallback((node: OpeningNode) => {
    setSelectedNode(node);
    setBoardFen(node.fen);
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
    if (!selectedNode || !selectedRepertoireId) return;

    // Optimistic: update board FEN immediately so the piece stays in place
    setBoardFen(newFen);

    // Check if child with this FEN already exists
    const existingChild = selectedNode.children?.find(c => {
      const cFenParts = c.fen.split(' ').slice(0, 4).join(' ');
      const newFenParts = newFen.split(' ').slice(0, 4).join(' ');
      return cFenParts === newFenParts;
    });

    if (existingChild) {
      setSelectedNode(existingChild);
      return;
    }

    try {
      const newNode = await addNode(selectedNode.id, moveSan, moveUci, newFen);
      // Set the new node BEFORE fetching tree so the tree-load effect
      // won't reset to root (selectedNode will be non-null)
      setSelectedNode(newNode);
      await fetchTree(selectedRepertoireId);
    } catch (e: any) {
      // Revert optimistic update on error
      setBoardFen(selectedNode.fen);
      setSnackbar({ open: true, msg: e.message, severity: 'error' });
    }
  }, [selectedNode, selectedRepertoireId, addNode, fetchTree]);

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
      await deleteNode(nodeId);
      if (selectedRepertoireId) {
        await fetchTree(selectedRepertoireId);
        // Go to parent
        if (selectedNode?.parent_id && currentTree) {
          const parent = findNode(currentTree, selectedNode.parent_id);
          if (parent) handleNodeSelect(parent);
        }
      }
    } catch (e: any) {
      setSnackbar({ open: true, msg: e.message, severity: 'error' });
    }
  }, [deleteNode, selectedRepertoireId, fetchTree, selectedNode, currentTree, findNode, handleNodeSelect]);

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
      setSnackbar({ open: true, msg: 'Game linked!', severity: 'success' });
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
      <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: '100vh', bgcolor: '#1a1a1a' }}>
        <Typography sx={{ color: '#888' }}>Loading...</Typography>
      </Box>
    );
  }

  const selectedRep = repertoires.find(r => r.id === selectedRepertoireId);

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', minHeight: '100vh', bgcolor: '#1a1a1a' }}>
      {/* Main content */}
      <Box sx={{
        display: 'flex',
        flexDirection: { xs: 'column', lg: 'row' },
        flex: 1,
        p: { xs: 1, sm: 2 },
        gap: 2,
        pb: { xs: '80px', md: 2 }, // bottom nav spacer on mobile
      }}>
        {/* Left: Board */}
        <Box sx={{
          display: 'flex',
          justifyContent: 'center',
          flexShrink: 0,
        }}>
          <DebutBoard
            fen={boardFen}
            orientation={boardOrientation}
            onMove={handleBoardMove}
            customArrows={boardArrows}
            onReset={handleReset}
            onGoToStart={handleGoToStart}
            onPrev={handlePrev}
            onNext={handleNext}
            onGoToEnd={handleGoToEnd}
            onFlip={handleFlip}
          />
        </Box>

        {/* Right: Tree + Details */}
        <Box sx={{
          flex: 1,
          display: 'flex',
          flexDirection: 'column',
          bgcolor: '#222',
          borderRadius: 1,
          overflow: 'hidden',
          minWidth: 0,
          maxHeight: { lg: 'calc(100vh - 32px)' },
        }}>
          {/* Repertoire selector */}
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

          {/* Tree + Details split */}
          <Box sx={{
            display: 'flex',
            flexDirection: { xs: 'column', md: 'row' },
            flex: 1,
            minHeight: 0,
            overflow: 'hidden',
          }}>
            {/* Tree */}
            <Box sx={{
              flex: 1,
              borderRight: { md: '1px solid #333' },
              borderBottom: { xs: '1px solid #333', md: 'none' },
              overflow: 'auto',
              minHeight: { xs: 200, md: 0 },
              maxHeight: { xs: 300, md: 'none' },
            }}>
              <OpeningTree
                tree={currentTree}
                selectedNodeId={selectedNode?.id || null}
                onNodeSelect={handleNodeSelect}
                loading={treeLoading}
              />
            </Box>

            {/* Details */}
            <Box sx={{
              flex: 1,
              overflow: 'auto',
              minHeight: { xs: 200, md: 0 },
            }}>
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
              />
            </Box>
          </Box>
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
