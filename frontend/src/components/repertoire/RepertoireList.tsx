'use client';

/**
 * RepertoireList Component
 * Displays user's saved openings with filtering and management
 */

import React from 'react';
import {
  Box,
  ToggleButtonGroup,
  ToggleButton,
  Typography,
} from '@mui/material';
import { useTranslations } from 'next-intl';

import { RepertoireOpening, UpdateOpeningRequest } from '@/types/repertoire';
import RepertoireItem from './RepertoireItem';

interface RepertoireListProps {
  repertoire: RepertoireOpening[];
  colorFilter: 'white' | 'black' | 'all';
  onColorFilterChange: (color: 'white' | 'black' | 'all') => void;
  onUpdate: (openingId: string, updates: UpdateOpeningRequest) => Promise<void>;
  onRemove: (openingId: string) => Promise<void>;
}

export default function RepertoireList({
  repertoire,
  colorFilter,
  onColorFilterChange,
  onUpdate,
  onRemove,
}: RepertoireListProps) {
  const t = useTranslations();

  return (
    <Box>
      {/* Color Filter */}
      <Box sx={{ mb: 3 }}>
        <Typography variant="caption" sx={{ display: 'block', mb: 1, fontWeight: 500 }}>
          {t('repertoire.colorFilter.label')}
        </Typography>
        <ToggleButtonGroup
          value={colorFilter}
          exclusive
          onChange={(event, newColor) => {
            if (newColor !== null) {
              onColorFilterChange(newColor);
            }
          }}
          size="small"
          sx={{
            gap: 1,
            '& .MuiToggleButton-root': {
              textTransform: 'none',
              minWidth: '80px',
            },
          }}
        >
          <ToggleButton value="all">{t('repertoire.colorFilter.all')}</ToggleButton>
          <ToggleButton value="white">{t('repertoire.colorFilter.white')}</ToggleButton>
          <ToggleButton value="black">{t('repertoire.colorFilter.black')}</ToggleButton>
        </ToggleButtonGroup>
      </Box>

      {/* Empty State */}
      {repertoire.length === 0 ? (
        <Box
          sx={{
            textAlign: 'center',
            py: 4,
            px: 2,
            backgroundColor: 'action.hover',
            borderRadius: 1,
          }}
        >
          <Typography variant="body2" color="text.secondary">
            {t('repertoire.emptyState')}
          </Typography>
        </Box>
      ) : (
        /* Openings List */
        <Box
          sx={{
            display: 'flex',
            flexDirection: 'column',
            gap: 1,
          }}
        >
          {repertoire.map((opening) => (
            <RepertoireItem
              key={opening.id}
              opening={opening}
              onUpdate={onUpdate}
              onRemove={onRemove}
            />
          ))}
        </Box>
      )}
    </Box>
  );
}
