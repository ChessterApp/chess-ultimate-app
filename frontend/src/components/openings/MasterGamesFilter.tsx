'use client';

import React, { useState, useEffect, useRef } from 'react';
import { useTranslations } from 'next-intl';
import {
  Box, TextField, InputAdornment, Select, MenuItem, FormControl, Chip, Collapse, Slider, Typography, Tooltip,
} from '@mui/material';
import { Search, TuneRounded, LinkRounded } from '@mui/icons-material';

type ColorValue = '' | 'white' | 'black';

const INVERSE_COLOR: Record<ColorValue, ColorValue> = { '': '', white: 'black', black: 'white' };

/**
 * Compact 3-state color toggle (Any / ♔ white / ♚ black) that lives inside a
 * name input's end adornment. `linked` draws a dashed ring on the active
 * non-Any chip to signal it was auto-set by the other (linked) toggle.
 */
function ColorSegToggle({
  value,
  linked,
  anyLabel,
  tooltips,
  onSelect,
}: {
  value: ColorValue;
  linked: boolean;
  anyLabel: string;
  tooltips: { any: string; white: string; black: string };
  onSelect: (v: ColorValue) => void;
}) {
  const opt = {
    height: 24,
    minWidth: 28,
    px: 0.75,
    borderRadius: '6px',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    fontWeight: 600,
    lineHeight: 1,
    cursor: 'pointer',
    color: 'text.secondary',
    userSelect: 'none' as const,
  };
  const dashed = linked ? { outline: '1px dashed', outlineColor: 'primary.main', outlineOffset: '1px' } : {};
  return (
    <Box
      sx={{
        display: 'flex',
        gap: '2px',
        bgcolor: 'background.default',
        border: '1px solid',
        borderColor: 'divider',
        borderRadius: '8px',
        p: '2px',
      }}
    >
      <Tooltip title={tooltips.any} arrow>
        <Box
          onMouseDown={(e) => e.preventDefault()}
          onClick={() => onSelect('')}
          sx={{
            ...opt,
            fontSize: 11,
            ...(value === '' && { bgcolor: 'rgba(20,184,166,0.14)', color: 'primary.main' }),
          }}
        >
          {anyLabel}
        </Box>
      </Tooltip>
      <Tooltip title={tooltips.white} arrow>
        <Box
          onMouseDown={(e) => e.preventDefault()}
          onClick={() => onSelect('white')}
          sx={{
            ...opt,
            fontSize: 15,
            ...(value === 'white' && { bgcolor: '#e8e6e1', color: '#1a1a1a', ...dashed }),
          }}
        >
          ♔
        </Box>
      </Tooltip>
      <Tooltip title={tooltips.black} arrow>
        <Box
          onMouseDown={(e) => e.preventDefault()}
          onClick={() => onSelect('black')}
          sx={{
            ...opt,
            fontSize: 15,
            ...(value === 'black' && { bgcolor: '#0a0a0a', color: '#f5f5f5', boxShadow: 'inset 0 0 0 1px #3a3a3a', ...dashed }),
          }}
        >
          ♚
        </Box>
      </Tooltip>
    </Box>
  );
}

export interface MasterGamesFilterState {
  playerName: string;
  opponentName: string;
  playerColor: string;
  result: string;
  sortBy: string;
  whiteEloMin: number;
  whiteEloMax: number;
  blackEloMin: number;
  blackEloMax: number;
  dateFrom: string;
  dateTo: string;
  ecoCode: string;
  eventName: string;
}

interface MasterGamesFilterProps {
  filters: MasterGamesFilterState;
  onFilterChange: (filters: MasterGamesFilterState) => void;
}

export default function MasterGamesFilter({ filters, onFilterChange }: MasterGamesFilterProps) {
  const t = useTranslations('debut');
  // Which toggle the user last set — drives the dashed "auto-set" ring on the
  // other (linked) toggle. Cleared whenever the color filter is cleared.
  const [colorSetBy, setColorSetBy] = useState<'player' | 'opponent' | null>(null);
  const [localPlayerName, setLocalPlayerName] = useState(filters.playerName);
  const [localOpponentName, setLocalOpponentName] = useState(filters.opponentName);
  const [ratingExpanded, setRatingExpanded] = useState(false);
  const [localWhiteElo, setLocalWhiteElo] = useState<[number, number]>([filters.whiteEloMin, filters.whiteEloMax]);
  const [localBlackElo, setLocalBlackElo] = useState<[number, number]>([filters.blackEloMin, filters.blackEloMax]);
  const [advancedExpanded, setAdvancedExpanded] = useState(false);
  const [localDateFrom, setLocalDateFrom] = useState(filters.dateFrom);
  const [localDateTo, setLocalDateTo] = useState(filters.dateTo);
  const [localEcoCode, setLocalEcoCode] = useState(filters.ecoCode);
  const [localEventName, setLocalEventName] = useState(filters.eventName);

  // Always hold the latest filters to avoid stale closures in debounced callbacks
  const filtersRef = useRef(filters);
  filtersRef.current = filters;

  // Debounce player name input: only fire API call after 300ms of no typing
  // AND only if length is 0 (cleared) OR >= 3 characters
  useEffect(() => {
    const timer = setTimeout(() => {
      if (localPlayerName.length === 0 || localPlayerName.length >= 3) {
        onFilterChange({ ...filtersRef.current, playerName: localPlayerName });
      }
    }, 300);

    return () => clearTimeout(timer);
  }, [localPlayerName]);

  // Debounce opponent name input: same pattern as player name
  useEffect(() => {
    const timer = setTimeout(() => {
      if (localOpponentName.length === 0 || localOpponentName.length >= 3) {
        onFilterChange({ ...filtersRef.current, opponentName: localOpponentName });
      }
    }, 300);

    return () => clearTimeout(timer);
  }, [localOpponentName]);

  // Sync external filter changes (e.g., when parent resets filters)
  useEffect(() => {
    setLocalPlayerName(filters.playerName);
  }, [filters.playerName]);

  // Sync opponent name from parent
  useEffect(() => {
    setLocalOpponentName(filters.opponentName);
  }, [filters.opponentName]);

  // Debounce white ELO slider (300ms)
  useEffect(() => {
    const timer = setTimeout(() => {
      onFilterChange({ ...filtersRef.current, whiteEloMin: localWhiteElo[0], whiteEloMax: localWhiteElo[1] });
    }, 300);
    return () => clearTimeout(timer);
  }, [localWhiteElo]);

  // Debounce black ELO slider (300ms)
  useEffect(() => {
    const timer = setTimeout(() => {
      onFilterChange({ ...filtersRef.current, blackEloMin: localBlackElo[0], blackEloMax: localBlackElo[1] });
    }, 300);
    return () => clearTimeout(timer);
  }, [localBlackElo]);

  // Sync ELO ranges from parent
  useEffect(() => {
    setLocalWhiteElo([filters.whiteEloMin, filters.whiteEloMax]);
  }, [filters.whiteEloMin, filters.whiteEloMax]);

  useEffect(() => {
    setLocalBlackElo([filters.blackEloMin, filters.blackEloMax]);
  }, [filters.blackEloMin, filters.blackEloMax]);

  // Debounce date from filter
  useEffect(() => {
    const timer = setTimeout(() => {
      onFilterChange({ ...filtersRef.current, dateFrom: localDateFrom });
    }, 300);
    return () => clearTimeout(timer);
  }, [localDateFrom]);

  // Debounce date to filter
  useEffect(() => {
    const timer = setTimeout(() => {
      onFilterChange({ ...filtersRef.current, dateTo: localDateTo });
    }, 300);
    return () => clearTimeout(timer);
  }, [localDateTo]);

  // Debounce ECO code filter
  useEffect(() => {
    const timer = setTimeout(() => {
      if (localEcoCode.length === 0 || localEcoCode.length >= 2) {
        onFilterChange({ ...filtersRef.current, ecoCode: localEcoCode });
      }
    }, 300);
    return () => clearTimeout(timer);
  }, [localEcoCode]);

  // Debounce event name filter
  useEffect(() => {
    const timer = setTimeout(() => {
      if (localEventName.length === 0 || localEventName.length >= 3) {
        onFilterChange({ ...filtersRef.current, eventName: localEventName });
      }
    }, 300);
    return () => clearTimeout(timer);
  }, [localEventName]);

  // Sync new filters from parent
  useEffect(() => {
    setLocalDateFrom(filters.dateFrom);
  }, [filters.dateFrom]);

  useEffect(() => {
    setLocalDateTo(filters.dateTo);
  }, [filters.dateTo]);

  useEffect(() => {
    setLocalEcoCode(filters.ecoCode);
  }, [filters.ecoCode]);

  useEffect(() => {
    setLocalEventName(filters.eventName);
  }, [filters.eventName]);

  const playerColor = (filters.playerColor || '') as ColorValue;

  // Keep the dashed-ring source in sync when the filter is cleared externally.
  useEffect(() => {
    if (playerColor === '') setColorSetBy(null);
  }, [playerColor]);

  const setPlayerColor = (value: ColorValue, source: 'player' | 'opponent') => {
    setColorSetBy(value === '' ? null : source);
    onFilterChange({ ...filtersRef.current, playerColor: value });
  };

  const playerNameLabel = localPlayerName.trim() || t('colorFilterPlayer');
  const opponentNameLabel = localOpponentName.trim() || t('colorFilterOpponent');

  const resultOptions = [
    { value: '', label: t('anyResult') || 'Any Result' },
    { value: '1-0', label: t('whiteWins') || 'White Wins' },
    { value: '0-1', label: t('blackWins') || 'Black Wins' },
    { value: '1/2-1/2', label: t('draw') || 'Draw' },
  ];

  const sortOptions = [
    { value: 'rating', label: t('highestRated') },
    { value: 'date_desc', label: t('newestFirst') },
    { value: 'date_asc', label: t('oldestFirst') },
  ];

  const selectSx = {
    color: 'text.secondary',
    fontSize: 12,
    height: 32,
    '.MuiOutlinedInput-notchedOutline': { borderColor: 'divider' },
    '&:hover .MuiOutlinedInput-notchedOutline': { borderColor: 'text.secondary' },
    '&.Mui-focused .MuiOutlinedInput-notchedOutline': { borderColor: 'primary.main' },
    '.MuiSelect-icon': { color: 'text.secondary' },
  };

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.75, mb: 1 }}>
      {/* Player name search with debounce + 3-char minimum */}
      <Box>
        <TextField
          size="small"
          placeholder={t('searchPlayer')}
          value={localPlayerName}
          onChange={(e) => setLocalPlayerName(e.target.value)}
          InputProps={{
            startAdornment: (
              <InputAdornment position="start">
                <Search sx={{ fontSize: 18, color: 'primary.light' }} />
              </InputAdornment>
            ),
            endAdornment: (
              <InputAdornment position="end">
                <ColorSegToggle
                  value={playerColor}
                  linked={colorSetBy === 'opponent' && playerColor !== ''}
                  anyLabel={t('colorAny')}
                  tooltips={{
                    any: t('anyColor'),
                    white: t('playsWhite', { name: playerNameLabel }),
                    black: t('playsBlack', { name: playerNameLabel }),
                  }}
                  onSelect={(v) => setPlayerColor(v, 'player')}
                />
              </InputAdornment>
            ),
          }}
          sx={{
            '& .MuiOutlinedInput-root': {
              bgcolor: 'background.paper',
              borderRadius: 1.5,
              height: 36,
              '& fieldset': { borderColor: 'divider' },
              '&:hover fieldset': { borderColor: 'text.secondary' },
              '&.Mui-focused fieldset': { borderColor: 'primary.main' },
            },
            '& .MuiInputBase-input': {
              color: 'text.primary',
              fontSize: 13,
              '&::placeholder': { color: 'text.secondary', opacity: 1 },
            },
          }}
        />
        {localPlayerName.length > 0 && localPlayerName.length < 3 && (
          <Box sx={{ fontSize: 11, color: 'text.secondary', mt: 0.5, pl: 1 }}>
            {t('typeAtLeast') || 'Type at least 3 characters to search'}
          </Box>
        )}
      </Box>

      {/* Opponent name search (optional) - same pattern as player field */}
      <Box>
        <TextField
          size="small"
          placeholder={t('searchOpponent') || 'vs Opponent (optional)'}
          value={localOpponentName}
          onChange={(e) => setLocalOpponentName(e.target.value)}
          InputProps={{
            startAdornment: (
              <InputAdornment position="start">
                <Search sx={{ fontSize: 18, color: 'text.secondary' }} />
              </InputAdornment>
            ),
            endAdornment: (
              <InputAdornment position="end">
                <ColorSegToggle
                  value={INVERSE_COLOR[playerColor]}
                  linked={colorSetBy === 'player' && playerColor !== ''}
                  anyLabel={t('colorAny')}
                  tooltips={{
                    any: t('anyColor'),
                    white: t('playsWhite', { name: opponentNameLabel }),
                    black: t('playsBlack', { name: opponentNameLabel }),
                  }}
                  onSelect={(v) => setPlayerColor(INVERSE_COLOR[v], 'opponent')}
                />
              </InputAdornment>
            ),
          }}
          sx={{
            '& .MuiOutlinedInput-root': {
              bgcolor: 'background.paper',
              borderRadius: 1.5,
              height: 36,
              '& fieldset': { borderColor: 'divider' },
              '&:hover fieldset': { borderColor: 'text.secondary' },
              '&.Mui-focused fieldset': { borderColor: 'primary.main' },
            },
            '& .MuiInputBase-input': {
              color: 'text.primary',
              fontSize: 13,
              '&::placeholder': { color: 'text.secondary', opacity: 1 },
            },
          }}
        />
        {localOpponentName.length > 0 && localOpponentName.length < 3 && (
          <Box sx={{ fontSize: 11, color: 'text.secondary', mt: 0.5, pl: 1 }}>
            {t('typeAtLeast') || 'Type at least 3 characters to search'}
          </Box>
        )}
      </Box>

      {/* Linked-colors hint — shown while a color is active on either toggle */}
      {colorSetBy !== null && playerColor !== '' && (
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5, color: 'primary.main', fontSize: 11, px: 0.25 }}>
          <LinkRounded sx={{ fontSize: 14 }} />
          {t('colorsLinked')}
        </Box>
      )}

      {/* Result + Sort row */}
      <Box sx={{ display: 'flex', gap: 0.75 }}>
        <FormControl size="small" sx={{ flex: 1 }}>
          <Select
            value={filters.result}
            onChange={(e) => onFilterChange({ ...filters, result: e.target.value })}
            displayEmpty
            renderValue={(val) => val === '' ? <span style={{ opacity: 1 }}>{t('anyResult') || 'Any Result'}</span> : resultOptions.find(o => o.value === val)?.label}
            sx={{ ...selectSx, bgcolor: 'background.paper', borderRadius: 1.5 }}
            MenuProps={{ PaperProps: { sx: { bgcolor: 'background.paper', backgroundImage: 'none', color: 'text.secondary' } } }}
          >
            {resultOptions.map(opt => (
              <MenuItem key={opt.value} value={opt.value} sx={{ fontSize: 12 }}>
                {opt.label}
              </MenuItem>
            ))}
          </Select>
        </FormControl>

        <FormControl size="small" sx={{ flex: 1 }}>
          <Select
            value={filters.sortBy}
            onChange={(e) => onFilterChange({ ...filters, sortBy: e.target.value })}
            sx={{ ...selectSx, bgcolor: 'background.paper', borderRadius: 1.5 }}
            MenuProps={{ PaperProps: { sx: { bgcolor: 'background.paper', backgroundImage: 'none', color: 'text.secondary' } } }}
          >
            {sortOptions.map(opt => (
              <MenuItem key={opt.value} value={opt.value} sx={{ fontSize: 12 }}>
                {opt.label}
              </MenuItem>
            ))}
          </Select>
        </FormControl>
      </Box>

      {/* Rating section - collapsible */}
      <Box sx={{ mt: 0.5 }}>
        <Box sx={{ position: 'relative', display: 'inline-block' }}>
          <Chip
            icon={<TuneRounded sx={{ fontSize: 16 }} />}
            label={t('rating')}
            onClick={() => setRatingExpanded(!ratingExpanded)}
            sx={{
              height: 28,
              fontSize: 12,
              bgcolor: 'background.paper',
              color: 'text.secondary',
              border: '1px solid',
              borderColor: 'divider',
              cursor: 'pointer',
              '&:hover': { bgcolor: 'rgba(0,0,0,0.04)' },
              '& .MuiChip-icon': { color: 'primary.main' },
            }}
          />
          {/* Active indicator dot */}
          {(localWhiteElo[0] !== 0 || localWhiteElo[1] !== 3500 || localBlackElo[0] !== 0 || localBlackElo[1] !== 3500) && (
            <Box
              sx={{
                position: 'absolute',
                top: 4,
                right: 4,
                width: 6,
                height: 6,
                borderRadius: '50%',
                bgcolor: 'primary.main',
              }}
            />
          )}
        </Box>

        <Collapse in={ratingExpanded}>
          <Box sx={{ mt: 1, px: 1, py: 1.5, bgcolor: 'background.paper', borderRadius: 1.5, border: '1px solid', borderColor: 'divider' }}>
            {/* White ELO slider */}
            <Box sx={{ mb: 2 }}>
              <Typography variant="caption" sx={{ color: 'text.secondary', fontSize: 11, fontWeight: 600, mb: 0.5, display: 'block' }}>
                {t('whiteElo')}
              </Typography>
              <Typography variant="caption" sx={{ color: 'text.primary', fontSize: 12, mb: 1, display: 'block' }}>
                {localWhiteElo[0]} - {localWhiteElo[1]}
              </Typography>
              <Slider
                value={localWhiteElo}
                onChange={(_, newValue) => setLocalWhiteElo(newValue as [number, number])}
                min={0}
                max={3500}
                step={50}
                valueLabelDisplay="auto"
                sx={{
                  color: 'primary.main',
                  '& .MuiSlider-thumb': {
                    width: 16,
                    height: 16,
                  },
                  '& .MuiSlider-valueLabel': {
                    fontSize: 11,
                    bgcolor: 'primary.main',
                  },
                }}
              />
            </Box>

            {/* Black ELO slider */}
            <Box>
              <Typography variant="caption" sx={{ color: 'text.secondary', fontSize: 11, fontWeight: 600, mb: 0.5, display: 'block' }}>
                {t('blackElo')}
              </Typography>
              <Typography variant="caption" sx={{ color: 'text.primary', fontSize: 12, mb: 1, display: 'block' }}>
                {localBlackElo[0]} - {localBlackElo[1]}
              </Typography>
              <Slider
                value={localBlackElo}
                onChange={(_, newValue) => setLocalBlackElo(newValue as [number, number])}
                min={0}
                max={3500}
                step={50}
                valueLabelDisplay="auto"
                sx={{
                  color: 'primary.main',
                  '& .MuiSlider-thumb': {
                    width: 16,
                    height: 16,
                  },
                  '& .MuiSlider-valueLabel': {
                    fontSize: 11,
                    bgcolor: 'primary.main',
                  },
                }}
              />
            </Box>
          </Box>
        </Collapse>
      </Box>

      {/* Advanced filters section - collapsible */}
      <Box sx={{ mt: 0.5 }}>
        <Box sx={{ position: 'relative', display: 'inline-block' }}>
          <Chip
            icon={<TuneRounded sx={{ fontSize: 16 }} />}
            label={t('masterGamesAdvanced') || 'Advanced Filters'}
            onClick={() => setAdvancedExpanded(!advancedExpanded)}
            sx={{
              height: 28,
              fontSize: 12,
              bgcolor: 'background.paper',
              color: 'text.secondary',
              border: '1px solid',
              borderColor: 'divider',
              cursor: 'pointer',
              '&:hover': { bgcolor: 'rgba(0,0,0,0.04)' },
              '& .MuiChip-icon': { color: 'primary.main' },
            }}
          />
          {/* Active indicator dot */}
          {(localDateFrom || localDateTo || localEcoCode || localEventName) && (
            <Box
              sx={{
                position: 'absolute',
                top: 4,
                right: 4,
                width: 6,
                height: 6,
                borderRadius: '50%',
                bgcolor: 'primary.main',
              }}
            />
          )}
        </Box>

        <Collapse in={advancedExpanded}>
          <Box sx={{ mt: 1, px: 1, py: 1.5, bgcolor: 'background.paper', borderRadius: 1.5, border: '1px solid', borderColor: 'divider' }}>
            {/* Date range filters */}
            <Box sx={{ display: 'flex', gap: 1, mb: 2 }}>
              <TextField
                size="small"
                placeholder={t('masterGamesDateFrom') || 'From year (e.g. 2020)'}
                value={localDateFrom}
                onChange={(e) => setLocalDateFrom(e.target.value)}
                sx={{
                  flex: 1,
                  '& .MuiOutlinedInput-root': {
                    bgcolor: 'background.default',
                    height: 36,
                    '& fieldset': { borderColor: 'divider' },
                    '&:hover fieldset': { borderColor: 'text.secondary' },
                    '&.Mui-focused fieldset': { borderColor: 'primary.main' },
                  },
                  '& .MuiInputBase-input': {
                    color: 'text.primary',
                    fontSize: 13,
                    '&::placeholder': { color: 'text.secondary', opacity: 1 },
                  },
                }}
              />
              <TextField
                size="small"
                placeholder={t('masterGamesDateTo') || 'To year (e.g. 2024)'}
                value={localDateTo}
                onChange={(e) => setLocalDateTo(e.target.value)}
                sx={{
                  flex: 1,
                  '& .MuiOutlinedInput-root': {
                    bgcolor: 'background.default',
                    height: 36,
                    '& fieldset': { borderColor: 'divider' },
                    '&:hover fieldset': { borderColor: 'text.secondary' },
                    '&.Mui-focused fieldset': { borderColor: 'primary.main' },
                  },
                  '& .MuiInputBase-input': {
                    color: 'text.primary',
                    fontSize: 13,
                    '&::placeholder': { color: 'text.secondary', opacity: 1 },
                  },
                }}
              />
            </Box>

            {/* ECO code and Event name filters */}
            <Box sx={{ display: 'flex', gap: 1 }}>
              <TextField
                size="small"
                placeholder={t('masterGamesEcoCode') || 'ECO code (e.g. B90)'}
                value={localEcoCode}
                onChange={(e) => setLocalEcoCode(e.target.value)}
                sx={{
                  flex: 1,
                  '& .MuiOutlinedInput-root': {
                    bgcolor: 'background.default',
                    height: 36,
                    '& fieldset': { borderColor: 'divider' },
                    '&:hover fieldset': { borderColor: 'text.secondary' },
                    '&.Mui-focused fieldset': { borderColor: 'primary.main' },
                  },
                  '& .MuiInputBase-input': {
                    color: 'text.primary',
                    fontSize: 13,
                    '&::placeholder': { color: 'text.secondary', opacity: 1 },
                  },
                }}
              />
              <TextField
                size="small"
                placeholder={t('masterGamesEvent') || 'Event (e.g. World Ch)'}
                value={localEventName}
                onChange={(e) => setLocalEventName(e.target.value)}
                sx={{
                  flex: 1,
                  '& .MuiOutlinedInput-root': {
                    bgcolor: 'background.default',
                    height: 36,
                    '& fieldset': { borderColor: 'divider' },
                    '&:hover fieldset': { borderColor: 'text.secondary' },
                    '&.Mui-focused fieldset': { borderColor: 'primary.main' },
                  },
                  '& .MuiInputBase-input': {
                    color: 'text.primary',
                    fontSize: 13,
                    '&::placeholder': { color: 'text.secondary', opacity: 1 },
                  },
                }}
              />
            </Box>
            {localEcoCode.length > 0 && localEcoCode.length < 2 && (
              <Box sx={{ fontSize: 11, color: 'text.secondary', mt: 0.5, pl: 1 }}>
                {t('typeAtLeast2') || 'Type at least 2 characters'}
              </Box>
            )}
            {localEventName.length > 0 && localEventName.length < 3 && (
              <Box sx={{ fontSize: 11, color: 'text.secondary', mt: 0.5, pl: 1 }}>
                {t('typeAtLeast') || 'Type at least 3 characters to search'}
              </Box>
            )}
          </Box>
        </Collapse>
      </Box>
    </Box>
  );
}
