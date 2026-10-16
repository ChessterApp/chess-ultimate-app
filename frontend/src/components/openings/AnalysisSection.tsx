/**
 * AnalysisSection — saved variations (event = 'Variation') listed above the
 * Games table in My Games: a collapsible header, the top rows as a compact
 * list, and "Show all" to page through the rest.
 */

'use client';

import React, { useMemo, useState } from 'react';
import { Box, Typography, IconButton, Button, ButtonBase, CircularProgress, Pagination } from '@mui/material';
import { ArrowDropDown, AccountTree, Edit, Delete } from '@mui/icons-material';
import { useLocale, useTranslations } from 'next-intl';
import { Chess } from 'chess.js';
import type { UserGame } from '@/hooks/useUserGames';

const PREVIEW_ROWS = 3;
const PREVIEW_PLIES = 10;
const ACCENT = '#7c3aed';

// ─── Collapsible section header (shared with the Games section) ───

interface SectionHeaderProps {
  icon: React.ReactNode;
  label: string;
  count: number;
  open: boolean;
  onToggle: () => void;
  /** Rendered at the right edge, outside the toggle button. */
  actions?: React.ReactNode;
}

export function SectionHeader({ icon, label, count, open, onToggle, actions }: SectionHeaderProps) {
  return (
    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, minHeight: 32 }}>
      <ButtonBase
        onClick={onToggle}
        aria-expanded={open}
        sx={{
          display: 'flex',
          alignItems: 'center',
          gap: 0.75,
          borderRadius: 1,
          pr: 0.75,
          '&.Mui-focusVisible': { outline: `2px solid ${ACCENT}`, outlineOffset: 2 },
        }}
      >
        <ArrowDropDown
          sx={{
            fontSize: 20,
            color: 'text.secondary',
            transform: open ? 'none' : 'rotate(-90deg)',
            transition: 'transform 0.15s',
          }}
        />
        {icon}
        <Typography component="span" sx={{ fontSize: 14, fontWeight: 700, color: 'text.primary' }}>
          {label}
        </Typography>
        <Box
          component="span"
          sx={{
            fontSize: 11,
            fontWeight: 600,
            color: 'text.secondary',
            bgcolor: 'rgba(255,255,255,0.06)',
            borderRadius: 10,
            px: 0.875,
            lineHeight: '20px',
          }}
        >
          {count}
        </Box>
      </ButtonBase>
      <Box sx={{ flex: 1 }} />
      {actions}
    </Box>
  );
}

// ─── Row helpers ───

/** First few mainline moves in SAN ("1. e4 c5 2. Nf3") and the mainline ply count. */
export function summarizeLine(pgn: string): { line: string; plies: number } {
  const chess = new Chess();
  try {
    chess.loadPgn(pgn);
  } catch {
    return { line: '', plies: 0 };
  }
  const moves = chess.history({ verbose: true });
  const line = moves.slice(0, PREVIEW_PLIES).map((m, i) => {
    const moveNumber = m.before.split(' ')[5];
    if (m.color === 'w') return `${moveNumber}. ${m.san}`;
    return i === 0 ? `${moveNumber}... ${m.san}` : m.san;
  }).join(' ');
  return { line: moves.length > PREVIEW_PLIES ? `${line} …` : line, plies: moves.length };
}

/** "today" / "yesterday" / "3 days ago" within a week, else a short date. */
export function formatEdited(iso: string, locale: string, now = new Date()): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return '';
  const startOfDay = (d: Date) => new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
  const days = Math.round((startOfDay(now) - startOfDay(date)) / 86_400_000);
  if (days >= 0 && days < 7) {
    return new Intl.RelativeTimeFormat(locale, { numeric: 'auto' }).format(-days, 'day');
  }
  return date.toLocaleDateString(locale, { day: 'numeric', month: 'short' });
}

// ─── Section ───

interface AnalysisSectionProps {
  games: UserGame[];
  total: number;
  page: number;
  perPage: number;
  loading: boolean;
  /** Initial open state until the user toggles the header. */
  defaultOpen?: boolean;
  onPageChange: (page: number) => void;
  onOpenGame: (game: UserGame) => void;
  /** Owner mode only — omitted in shared (read-only) views. */
  onAddVariation?: () => void;
  onEdit?: (e: React.MouseEvent, game: UserGame) => void;
  onDelete?: (e: React.MouseEvent, game: UserGame) => void;
}

export default function AnalysisSection({
  games, total, page, perPage, loading, defaultOpen = true,
  onPageChange, onOpenGame, onAddVariation, onEdit, onDelete,
}: AnalysisSectionProps) {
  const t = useTranslations('debut');
  const locale = useLocale();
  const [userOpen, setUserOpen] = useState<boolean | null>(null);
  const [showAll, setShowAll] = useState(false);
  const open = userOpen ?? defaultOpen;

  const rows = useMemo(() => (showAll ? games : games.slice(0, PREVIEW_ROWS)), [games, showAll]);
  const summaries = useMemo(
    () => new Map(rows.map(g => [g.id, summarizeLine(g.pgn)])),
    [rows],
  );
  const totalPages = Math.ceil(total / Math.max(perPage, 1));

  const toggleShowAll = () => {
    if (showAll && page !== 1) onPageChange(1);
    setShowAll(!showAll);
  };

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
      <SectionHeader
        icon={<AccountTree sx={{ fontSize: 18, color: 'text.secondary' }} />}
        label={t('myGames.analysis')}
        count={total}
        open={open}
        onToggle={() => setUserOpen(!open)}
        actions={
          <>
            {open && total > PREVIEW_ROWS && (
              <Button
                size="small"
                onClick={toggleShowAll}
                sx={{ fontSize: 12, textTransform: 'none', color: ACCENT, minWidth: 0, px: 1 }}
              >
                {showAll ? t('myGames.showLess') : t('myGames.showAll', { count: total })}
              </Button>
            )}
            {onAddVariation && (
              <Button
                variant="outlined"
                size="small"
                startIcon={<AccountTree />}
                onClick={onAddVariation}
                sx={{
                  fontSize: 12,
                  textTransform: 'none',
                  py: 0.25,
                  color: ACCENT,
                  borderColor: ACCENT,
                  whiteSpace: 'nowrap',
                  '&:hover': { borderColor: '#6d28d9', bgcolor: 'rgba(124,58,237,0.06)' },
                }}
              >
                {t('myGames.addVariation')}
              </Button>
            )}
          </>
        }
      />

      {open && loading && (
        <Box sx={{ display: 'flex', justifyContent: 'center', py: 2 }}>
          <CircularProgress size={22} />
        </Box>
      )}

      {open && !loading && games.length === 0 && (
        <Typography variant="body2" sx={{ color: 'text.secondary', fontSize: 12, px: 1, py: 1 }}>
          {t('myGames.noAnalysis')}
        </Typography>
      )}

      {open && !loading && games.length > 0 && (
        <Box sx={{ border: '1px solid rgba(255,255,255,0.08)', borderRadius: 1.5, overflow: 'hidden' }}>
          {rows.map((game, i) => {
            const { line, plies } = summaries.get(game.id) ?? { line: '', plies: 0 };
            const edited = formatEdited(game.updated_at || game.created_at, locale);
            return (
              <Box
                key={game.id}
                role="button"
                tabIndex={0}
                onClick={() => onOpenGame(game)}
                onKeyDown={(e) => {
                  if (e.target !== e.currentTarget) return;
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    onOpenGame(game);
                  }
                }}
                sx={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 1.25,
                  px: 1.25,
                  py: 0.875,
                  cursor: 'pointer',
                  borderTop: i === 0 ? 0 : '1px solid rgba(255,255,255,0.04)',
                  '&:hover': { bgcolor: 'rgba(255,255,255,0.06)' },
                  '&:hover .row-actions': { opacity: 1 },
                  '&:focus-visible': { outline: `2px solid ${ACCENT}`, outlineOffset: -2 },
                }}
              >
                <Box sx={{ width: 3, alignSelf: 'stretch', borderRadius: 3, background: 'linear-gradient(#7c3aed, #6366f1)' }} />
                <Box sx={{ flex: 1, minWidth: 0 }}>
                  <Typography
                    noWrap
                    sx={{ fontSize: 13, fontWeight: 500, color: game.title ? 'text.primary' : 'text.disabled' }}
                  >
                    {game.title || t('myGames.untitledVariation')}
                  </Typography>
                  {line && (
                    <Typography noWrap sx={{ fontSize: 11, fontFamily: 'monospace', color: 'text.secondary' }}>
                      {line}
                    </Typography>
                  )}
                </Box>
                <Typography sx={{ fontSize: 11, color: 'text.secondary', whiteSpace: 'nowrap' }}>
                  {[t('myGames.plyCount', { count: plies }), edited].filter(Boolean).join(' · ')}
                </Typography>
                {(onEdit || onDelete) && (
                  <Box
                    className="row-actions"
                    sx={{ display: 'flex', gap: 0.25, opacity: { xs: 1, md: 0 }, transition: 'opacity 0.15s' }}
                  >
                    {onEdit && (
                      <IconButton size="small" onClick={(e) => { e.stopPropagation(); onEdit(e, game); }} sx={{ p: 0.5 }} aria-label="edit game">
                        <Edit sx={{ fontSize: 14, color: 'text.secondary' }} />
                      </IconButton>
                    )}
                    {onDelete && (
                      <IconButton size="small" onClick={(e) => { e.stopPropagation(); onDelete(e, game); }} sx={{ p: 0.5 }} aria-label="delete game">
                        <Delete sx={{ fontSize: 14, color: 'text.secondary', '&:hover': { color: 'error.main' } }} />
                      </IconButton>
                    )}
                  </Box>
                )}
              </Box>
            );
          })}
        </Box>
      )}

      {open && showAll && totalPages > 1 && (
        <Box sx={{ display: 'flex', justifyContent: 'center' }}>
          <Pagination
            count={totalPages}
            page={page}
            onChange={(_, p) => onPageChange(p)}
            size="small"
            sx={{ '& .MuiPaginationItem-root': { fontSize: 12 } }}
          />
        </Box>
      )}
    </Box>
  );
}
