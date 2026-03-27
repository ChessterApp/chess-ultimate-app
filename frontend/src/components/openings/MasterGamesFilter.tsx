'use client';

import React, { useState, useEffect } from 'react';
import { useTranslations } from 'next-intl';
import {
  Box, TextField, InputAdornment, Select, MenuItem, FormControl, Chip, Collapse, Slider, Typography,
} from '@mui/material';
import { Search, TuneRounded } from '@mui/icons-material';

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

  // Debounce player name input: only fire API call after 300ms of no typing
  // AND only if length is 0 (cleared) OR >= 3 characters
  useEffect(() => {
    const timer = setTimeout(() => {
      if (localPlayerName.length === 0 || localPlayerName.length >= 3) {
        onFilterChange({ ...filters, playerName: localPlayerName });
      }
    }, 300);

    return () => clearTimeout(timer);
  }, [localPlayerName]);

  // Debounce opponent name input: same pattern as player name
  useEffect(() => {
    const timer = setTimeout(() => {
      if (localOpponentName.length === 0 || localOpponentName.length >= 3) {
        onFilterChange({ ...filters, opponentName: localOpponentName });
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
      onFilterChange({ ...filters, whiteEloMin: localWhiteElo[0], whiteEloMax: localWhiteElo[1] });
    }, 300);
    return () => clearTimeout(timer);
  }, [localWhiteElo]);

  // Debounce black ELO slider (300ms)
  useEffect(() => {
    const timer = setTimeout(() => {
      onFilterChange({ ...filters, blackEloMin: localBlackElo[0], blackEloMax: localBlackElo[1] });
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
      onFilterChange({ ...filters, dateFrom: localDateFrom });
    }, 300);
    return () => clearTimeout(timer);
  }, [localDateFrom]);

  // Debounce date to filter
  useEffect(() => {
    const timer = setTimeout(() => {
      onFilterChange({ ...filters, dateTo: localDateTo });
    }, 300);
    return () => clearTimeout(timer);
  }, [localDateTo]);

  // Debounce ECO code filter
  useEffect(() => {
    const timer = setTimeout(() => {
      if (localEcoCode.length === 0 || localEcoCode.length >= 2) {
        onFilterChange({ ...filters, ecoCode: localEcoCode });
      }
    }, 300);
    return () => clearTimeout(timer);
  }, [localEcoCode]);

  // Debounce event name filter
  useEffect(() => {
    const timer = setTimeout(() => {
      if (localEventName.length === 0 || localEventName.length >= 3) {
        onFilterChange({ ...filters, eventName: localEventName });
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

  const colorOptions = [
    { value: '', label: t('anyColor') || 'Any Color' },
    { value: 'white', label: t('whiteGames') || 'White Games' },
    { value: 'black', label: t('blackGames') || 'Black Games' },
  ];

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

      {/* Player Color + Result + Sort row */}
      <Box sx={{ display: 'flex', gap: 0.75 }}>
        <FormControl size="small" sx={{ flex: 1 }}>
          <Select
            value={filters.playerColor}
            onChange={(e) => onFilterChange({ ...filters, playerColor: e.target.value })}
            displayEmpty
            renderValue={(val) => val === '' ? <span style={{ opacity: 1 }}>{t('anyColor') || 'Any Color'}</span> : colorOptions.find(o => o.value === val)?.label}
            sx={{ ...selectSx, bgcolor: 'background.paper', borderRadius: 1.5 }}
            MenuProps={{ PaperProps: { sx: { bgcolor: 'background.paper', backgroundImage: 'none', color: 'text.secondary' } } }}
          >
            {colorOptions.map(opt => (
              <MenuItem key={opt.value} value={opt.value} sx={{ fontSize: 12 }}>
                {opt.label}
              </MenuItem>
            ))}
          </Select>
        </FormControl>

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
