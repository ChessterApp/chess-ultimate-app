'use client';

import React from 'react';
import { useTranslations } from 'next-intl';
import {
  Box, TextField, InputAdornment, Select, MenuItem, FormControl,
} from '@mui/material';
import { Search } from '@mui/icons-material';

export interface MasterGamesFilterState {
  playerName: string;
  playerColor: string;
  sortBy: string;
}

interface MasterGamesFilterProps {
  filters: MasterGamesFilterState;
  onFilterChange: (filters: MasterGamesFilterState) => void;
}

export default function MasterGamesFilter({ filters, onFilterChange }: MasterGamesFilterProps) {
  const t = useTranslations('debut');

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
    color: '#ccc',
    fontSize: 12,
    height: 32,
    '.MuiOutlinedInput-notchedOutline': { borderColor: '#444' },
    '&:hover .MuiOutlinedInput-notchedOutline': { borderColor: '#666' },
    '&.Mui-focused .MuiOutlinedInput-notchedOutline': { borderColor: '#5c6bc0' },
    '.MuiSelect-icon': { color: '#888' },
  };

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.75, mb: 1 }}>
      {/* Player name search — immediate update to avoid dropped debounce updates */}
      <TextField
        size="small"
        placeholder={t('searchPlayer')}
        value={filters.playerName}
        onChange={(e) => onFilterChange({ ...filters, playerName: e.target.value })}
        InputProps={{
          startAdornment: (
            <InputAdornment position="start">
              <Search sx={{ fontSize: 18, color: '#7986cb' }} />
            </InputAdornment>
          ),
        }}
        sx={{
          '& .MuiOutlinedInput-root': {
            bgcolor: '#2a2a2a',
            borderRadius: 1.5,
            height: 36,
            '& fieldset': { borderColor: '#444' },
            '&:hover fieldset': { borderColor: '#666' },
            '&.Mui-focused fieldset': { borderColor: '#5c6bc0' },
          },
          '& .MuiInputBase-input': {
            color: '#e0e0e0',
            fontSize: 13,
            '&::placeholder': { color: '#888', opacity: 1 },
          },
        }}
      />

      {/* Player Color + Sort row */}
      <Box sx={{ display: 'flex', gap: 0.75 }}>
        <FormControl size="small" sx={{ flex: 1 }}>
          <Select
            value={filters.playerColor}
            onChange={(e) => onFilterChange({ ...filters, playerColor: e.target.value })}
            sx={{ ...selectSx, bgcolor: '#2a2a2a', borderRadius: 1.5 }}
            MenuProps={{ PaperProps: { sx: { bgcolor: '#333', color: '#ccc' } } }}
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
            sx={{ ...selectSx, bgcolor: '#2a2a2a', borderRadius: 1.5 }}
            MenuProps={{ PaperProps: { sx: { bgcolor: '#333', color: '#ccc' } } }}
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
