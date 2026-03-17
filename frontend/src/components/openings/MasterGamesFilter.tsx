'use client';

import React, { useState, useEffect } from 'react';
import { useTranslations } from 'next-intl';
import {
  Box, TextField, InputAdornment, Select, MenuItem, FormControl,
} from '@mui/material';
import { Search } from '@mui/icons-material';

export interface MasterGamesFilterState {
  playerName: string;
  opponentName: string;
  playerColor: string;
  sortBy: string;
}

interface MasterGamesFilterProps {
  filters: MasterGamesFilterState;
  onFilterChange: (filters: MasterGamesFilterState) => void;
}

export default function MasterGamesFilter({ filters, onFilterChange }: MasterGamesFilterProps) {
  const t = useTranslations('debut');
  const [localPlayerName, setLocalPlayerName] = useState(filters.playerName);
  const [localOpponentName, setLocalOpponentName] = useState(filters.opponentName);

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

  const colorOptions = [
    { value: '', label: t('anyColor') || 'Any Color' },
    { value: 'white', label: t('whiteGames') || 'White Games' },
    { value: 'black', label: t('blackGames') || 'Black Games' },
  ];

  const sortOptions = [
    { value: 'rating', label: t('highestRated') },
    { value: 'date_desc', label: t('newestFirst') },
    { value: 'date_asc', label: t('oldestFirst') },
    { value: 'elo_white', label: t('whiteRating') },
    { value: 'elo_black', label: t('blackRating') },
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

      {/* Player Color + Sort row */}
      <Box sx={{ display: 'flex', gap: 0.75 }}>
        <FormControl size="small" sx={{ flex: 1 }}>
          <Select
            value={filters.playerColor}
            onChange={(e) => onFilterChange({ ...filters, playerColor: e.target.value })}
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
    </Box>
  );
}
