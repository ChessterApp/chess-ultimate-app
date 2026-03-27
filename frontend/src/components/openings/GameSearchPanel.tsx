'use client';

import React, { useState, useRef } from 'react';
import {
  Dialog, DialogTitle, DialogContent, IconButton, Box, Typography,
  TextField, Button, Slider, Tabs, Tab, CircularProgress, Chip,
  List, ListItem, ListItemText, Collapse, Divider, Select, MenuItem, FormControl,
} from '@mui/material';
import { Close, Link as LinkIcon, ExpandMore, ExpandLess } from '@mui/icons-material';
import { useTranslations } from 'next-intl';
import type { GameSearchResult } from '@/hooks/useOpeningRepertoire';

interface GameSearchPanelProps {
  fen: string;
  onLinkGame: (game: GameSearchResult) => Promise<void>;
  open: boolean;
  onClose: () => void;
  onSearch: (
    source: string,
    fen: string,
    opts: {
      username?: string;
      minRating?: number;
      maxGames?: number;
      archiveMonths?: number;
      playerColor?: string;
      resultFilter?: string;
    } | undefined,
    onGame: (game: GameSearchResult) => void,
    onProgress: (p: { checked: number; found: number }) => void,
  ) => () => void;
  fetchGamePgn?: (gameId: number) => Promise<string>;
}

export default function GameSearchPanel({ fen, onLinkGame, open, onClose, onSearch, fetchGamePgn }: GameSearchPanelProps) {
  const [source, setSource] = useState(0); // 0=internal, 1=lichess, 2=chesscom
  const [username, setUsername] = useState('');
  const [minRating, setMinRating] = useState(2000);
  const [maxGames, setMaxGames] = useState(10);
  const [searching, setSearching] = useState(false);
  const [games, setGames] = useState<GameSearchResult[]>([]);
  const [progress, setProgress] = useState({ checked: 0, found: 0 });
  const [expandedPgn, setExpandedPgn] = useState<string | null>(null);
  const [loadedPgns, setLoadedPgns] = useState<Record<string, string>>({});
  const [loadingPgnId, setLoadingPgnId] = useState<string | null>(null);
  const abortRef = useRef<(() => void) | null>(null);

  // New filters for Lichess/Chess.com
  const [archiveMonths, setArchiveMonths] = useState(3); // Default 3 months
  const [playerColor, setPlayerColor] = useState(''); // white/black/both
  const [resultFilter, setResultFilter] = useState(''); // win/draw/loss/all

  const sourceNames = ['internal', 'lichess', 'chesscom'];
  const t = useTranslations('debut');

  const handleSearch = () => {
    setGames([]);
    setProgress({ checked: 0, found: 0 });
    setSearching(true);

    const abort = onSearch(
      sourceNames[source],
      fen,
      {
        username: source > 0 ? username : undefined,
        minRating,
        maxGames,
        archiveMonths: source > 0 ? archiveMonths : undefined,
        playerColor: source > 0 ? playerColor : undefined,
        resultFilter: source > 0 ? resultFilter : undefined,
      },
      (game) => setGames(prev => [...prev, game]),
      (p) => setProgress(p),
    );

    abortRef.current = abort;

    // Auto-stop after 30s
    setTimeout(() => {
      setSearching(false);
    }, 30000);
  };

  const handleStop = () => {
    abortRef.current?.();
    setSearching(false);
  };

  const handleClose = () => {
    handleStop();
    onClose();
  };

  return (
    <Dialog
      open={open}
      onClose={handleClose}
      fullWidth
      maxWidth="md"
      PaperProps={{ sx: { bgcolor: 'background.default', color: 'text.primary', minHeight: 500 } }}
    >
      <DialogTitle sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', pb: 1 }}>
        Search Games by Position
        <IconButton onClick={handleClose} sx={{ color: 'text.secondary' }}><Close /></IconButton>
      </DialogTitle>

      <DialogContent sx={{ display: 'flex', flexDirection: 'column', gap: 1.5 }}>
        {/* FEN display */}
        <Typography variant="caption" sx={{ fontFamily: 'monospace', color: 'text.disabled', fontSize: 10, wordBreak: 'break-all' }}>
          FEN: {fen}
        </Typography>

        {/* Source tabs */}
        <Tabs
          value={source}
          onChange={(_, v) => setSource(v)}
          sx={{
            '& .MuiTab-root': { color: 'text.secondary', fontSize: 12, minHeight: 36, textTransform: 'none' },
            '& .Mui-selected': { color: 'primary.light' },
            '& .MuiTabs-indicator': { bgcolor: 'primary.light' },
          }}
        >
          <Tab label="Master Games" />
          <Tab label="Lichess" />
          <Tab label="Chess.com" />
        </Tabs>

        {/* Search controls */}
        <Box sx={{ display: 'flex', gap: 1, alignItems: 'flex-end', flexWrap: 'wrap' }}>
          {source > 0 && (
            <TextField
              label="Username"
              value={username}
              onChange={e => setUsername(e.target.value)}
              size="small"
              sx={{
                width: 180,
                '& .MuiInputBase-root': { color: 'text.primary', bgcolor: 'action.hover' },
                '& .MuiOutlinedInput-notchedOutline': { borderColor: 'divider' },
                '& .MuiInputLabel-root': { color: 'text.secondary' },
              }}
            />
          )}

          <Box sx={{ width: 140 }}>
            <Typography variant="caption" sx={{ color: 'text.secondary', fontSize: 10 }}>Min Rating: {minRating}</Typography>
            <Slider
              value={minRating}
              onChange={(_, v) => setMinRating(v as number)}
              min={0}
              max={2800}
              step={100}
              size="small"
              sx={{ color: 'primary.light' }}
            />
          </Box>

          <Box sx={{ width: 100 }}>
            <Typography variant="caption" sx={{ color: 'text.secondary', fontSize: 10 }}>Max: {maxGames}</Typography>
            <Slider
              value={maxGames}
              onChange={(_, v) => setMaxGames(v as number)}
              min={1}
              max={50}
              size="small"
              sx={{ color: 'primary.light' }}
            />
          </Box>

          {!searching ? (
            <Button
              variant="contained"
              size="small"
              onClick={handleSearch}
              disabled={source > 0 && !username.trim()}
              sx={{ height: 36 }}
            >
              Search
            </Button>
          ) : (
            <Button
              variant="outlined"
              size="small"
              onClick={handleStop}
              color="warning"
              sx={{ height: 36 }}
            >
              Stop
            </Button>
          )}
        </Box>

        {/* Additional filters for Lichess/Chess.com */}
        {source > 0 && (
          <Box sx={{ display: 'flex', gap: 1, alignItems: 'center', flexWrap: 'wrap', mt: 1 }}>
            <FormControl size="small" sx={{ minWidth: 130 }}>
              <Select
                value={archiveMonths}
                onChange={(e) => setArchiveMonths(e.target.value as number)}
                sx={{
                  color: 'text.secondary',
                  fontSize: 12,
                  height: 32,
                  bgcolor: 'action.hover',
                  '.MuiOutlinedInput-notchedOutline': { borderColor: 'divider' },
                }}
              >
                <MenuItem value={1} sx={{ fontSize: 12 }}>{t('onlineSearchFilters.period1Month') || '1 month'}</MenuItem>
                <MenuItem value={3} sx={{ fontSize: 12 }}>{t('onlineSearchFilters.period3Months') || '3 months'}</MenuItem>
                <MenuItem value={6} sx={{ fontSize: 12 }}>{t('onlineSearchFilters.period6Months') || '6 months'}</MenuItem>
                <MenuItem value={12} sx={{ fontSize: 12 }}>{t('onlineSearchFilters.period12Months') || '12 months'}</MenuItem>
                <MenuItem value={24} sx={{ fontSize: 12 }}>{t('onlineSearchFilters.period24Months') || '24 months'}</MenuItem>
                <MenuItem value={36} sx={{ fontSize: 12 }}>{t('onlineSearchFilters.period36Months') || '36 months'}</MenuItem>
                <MenuItem value={999} sx={{ fontSize: 12 }}>{t('onlineSearchFilters.periodAll') || 'All'}</MenuItem>
              </Select>
            </FormControl>

            <FormControl size="small" sx={{ minWidth: 110 }}>
              <Select
                value={playerColor}
                onChange={(e) => setPlayerColor(e.target.value)}
                displayEmpty
                sx={{
                  color: 'text.secondary',
                  fontSize: 12,
                  height: 32,
                  bgcolor: 'action.hover',
                  '.MuiOutlinedInput-notchedOutline': { borderColor: 'divider' },
                }}
              >
                <MenuItem value="" sx={{ fontSize: 12 }}>{t('anyColor') || 'Any Color'}</MenuItem>
                <MenuItem value="white" sx={{ fontSize: 12 }}>{t('white') || 'White'}</MenuItem>
                <MenuItem value="black" sx={{ fontSize: 12 }}>{t('black') || 'Black'}</MenuItem>
              </Select>
            </FormControl>

            <FormControl size="small" sx={{ minWidth: 110 }}>
              <Select
                value={resultFilter}
                onChange={(e) => setResultFilter(e.target.value)}
                displayEmpty
                sx={{
                  color: 'text.secondary',
                  fontSize: 12,
                  height: 32,
                  bgcolor: 'action.hover',
                  '.MuiOutlinedInput-notchedOutline': { borderColor: 'divider' },
                }}
              >
                <MenuItem value="" sx={{ fontSize: 12 }}>{t('anyResult') || 'Any Result'}</MenuItem>
                <MenuItem value="win" sx={{ fontSize: 12 }}>{t('onlineSearchFilters.resultWin') || 'Win'}</MenuItem>
                <MenuItem value="draw" sx={{ fontSize: 12 }}>{t('draw') || 'Draw'}</MenuItem>
                <MenuItem value="loss" sx={{ fontSize: 12 }}>{t('onlineSearchFilters.resultLoss') || 'Loss'}</MenuItem>
              </Select>
            </FormControl>
          </Box>
        )}

        {/* Progress */}
        {(searching || progress.checked > 0) && (
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            {searching && <CircularProgress size={14} />}
            <Typography variant="caption" sx={{ color: 'text.secondary' }}>
              Checked {progress.checked} games · Found {progress.found} matches
            </Typography>
          </Box>
        )}

        {/* Results */}
        <Box sx={{ flex: 1, overflow: 'auto' }}>
          {games.length === 0 && !searching && progress.checked > 0 && (
            <Typography sx={{ color: 'text.disabled', textAlign: 'center', mt: 2 }}>
              No games found for this position.
            </Typography>
          )}

          <List dense sx={{ p: 0 }}>
            {games.map((game, idx) => (
              <React.Fragment key={`${game.id}-${idx}`}>
                <ListItem sx={{ px: 0, py: 0.5, flexDirection: 'column', alignItems: 'stretch' }}>
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, width: '100%' }}>
                    <Box sx={{ flex: 1 }}>
                      <Typography variant="body2" sx={{ color: 'text.primary', fontSize: 13 }}>
                        {game.white} ({game.white_elo || '?'}) vs {game.black} ({game.black_elo || '?'})
                      </Typography>
                      <Box sx={{ display: 'flex', gap: 0.5, alignItems: 'center', mt: 0.3 }}>
                        <Chip label={game.result || '?'} size="small" sx={{ height: 16, fontSize: 10, bgcolor: 'action.hover', color: 'text.secondary' }} />
                        {game.eco && <Chip label={game.eco} size="small" sx={{ height: 16, fontSize: 10, bgcolor: 'primary.dark', color: '#fff' }} />}
                        {game.date && <Typography variant="caption" sx={{ color: 'text.disabled', fontSize: 10 }}>{game.date}</Typography>}
                      </Box>
                    </Box>

                    <Button
                      size="small"
                      startIcon={<LinkIcon sx={{ fontSize: 14 }} />}
                      onClick={() => onLinkGame(game)}
                      sx={{ color: 'primary.light', fontSize: 11, textTransform: 'none', minWidth: 0 }}
                    >
                      Link
                    </Button>

                    {(game.pgn || game.pgn_offset !== undefined || loadedPgns[String(game.id)]) && (
                      <IconButton
                        size="small"
                        onClick={async () => {
                          const gid = String(game.id);
                          if (expandedPgn === gid) {
                            setExpandedPgn(null);
                            return;
                          }
                          // Lazy-load PGN if not available
                          if (!game.pgn && !loadedPgns[gid] && fetchGamePgn && game.id) {
                            setLoadingPgnId(gid);
                            try {
                              const pgn = await fetchGamePgn(Number(game.id));
                              setLoadedPgns(prev => ({ ...prev, [gid]: pgn }));
                            } catch { /* ignore */ }
                            setLoadingPgnId(null);
                          }
                          setExpandedPgn(gid);
                        }}
                        sx={{ color: 'text.disabled' }}
                      >
                        {loadingPgnId === String(game.id) ? <CircularProgress size={14} /> : expandedPgn === String(game.id) ? <ExpandLess /> : <ExpandMore />}
                      </IconButton>
                    )}
                  </Box>

                  {/* PGN view */}
                  <Collapse in={expandedPgn === String(game.id)}>
                    <Box sx={{ mt: 0.5, p: 1, bgcolor: 'action.hover', borderRadius: 1, maxHeight: 120, overflow: 'auto' }}>
                      <Typography variant="caption" sx={{ fontFamily: 'monospace', color: 'text.secondary', fontSize: 11, whiteSpace: 'pre-wrap' }}>
                        {(game.pgn || loadedPgns[String(game.id)] || '')?.slice(0, 1000)}
                      </Typography>
                    </Box>
                  </Collapse>
                </ListItem>
                {idx < games.length - 1 && <Divider sx={{ borderColor: 'divider' }} />}
              </React.Fragment>
            ))}
          </List>
        </Box>
      </DialogContent>
    </Dialog>
  );
}
