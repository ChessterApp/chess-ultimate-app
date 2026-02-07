'use client';

/**
 * RepertoireAccordion Component
 * Main container for opening repertoire feature
 * Positioned in Analysis tab with two sub-tabs:
 * - My Repertoire: View and manage saved openings
 * - Browse & Add: Search and add new openings
 */

import React, { useState } from 'react';
import {
  Accordion,
  AccordionSummary,
  AccordionDetails,
  Tabs,
  Tab,
  Box,
  CircularProgress,
  Alert,
  Typography,
} from '@mui/material';
import { ExpandMore, LibraryBooks } from '@mui/icons-material';
import { useTranslations } from 'next-intl';

import { useRepertoire } from '@/hooks/useRepertoire';
import RepertoireList from './RepertoireList';
import OpeningBrowser from './OpeningBrowser';

type TabValue = 'my-repertoire' | 'browse';

export default function RepertoireAccordion() {
  const t = useTranslations();
  const [activeTab, setActiveTab] = useState<TabValue>('my-repertoire');
  const [colorFilter, setColorFilter] = useState<'white' | 'black' | 'all'>('all');

  const {
    repertoire,
    loading,
    error,
    addToRepertoire,
    updateOpening,
    removeFromRepertoire,
  } = useRepertoire();

  // Filter repertoire by color
  const filteredRepertoire = repertoire.filter((opening) => {
    if (colorFilter === 'all') return true;
    return opening.color === colorFilter || opening.color === 'both';
  });

  const handleTabChange = (_event: React.SyntheticEvent, newValue: TabValue) => {
    setActiveTab(newValue);
  };

  const handleColorFilterChange = (newColor: 'white' | 'black' | 'all') => {
    setColorFilter(newColor);
  };

  return (
    <Accordion defaultExpanded={false} sx={{ width: '100%' }}>
      <AccordionSummary expandIcon={<ExpandMore />} sx={{ backgroundColor: 'action.hover' }}>
        <LibraryBooks sx={{ mr: 1.5, color: 'primary.main' }} />
        <Typography variant="subtitle1" sx={{ fontWeight: 500 }}>
          {t('analysis.sections.openingRepertoire')}
        </Typography>
      </AccordionSummary>

      <AccordionDetails sx={{ p: 2 }}>
        <Box sx={{ width: '100%' }}>
          {/* Error message */}
          {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}

          {/* Tab navigation */}
          <Tabs
            value={activeTab}
            onChange={handleTabChange}
            sx={{ borderBottom: 1, borderColor: 'divider', mb: 2 }}
          >
            <Tab
              label={t('repertoire.myRepertoire')}
              value="my-repertoire"
              sx={{ textTransform: 'none' }}
            />
            <Tab
              label={t('repertoire.browseAndAdd')}
              value="browse"
              sx={{ textTransform: 'none' }}
            />
          </Tabs>

          {/* Loading indicator */}
          {loading && activeTab === 'my-repertoire' && (
            <Box sx={{ display: 'flex', justifyContent: 'center', py: 3 }}>
              <CircularProgress />
            </Box>
          )}

          {/* My Repertoire Tab */}
          {!loading && activeTab === 'my-repertoire' && (
            <RepertoireList
              repertoire={filteredRepertoire}
              colorFilter={colorFilter}
              onColorFilterChange={handleColorFilterChange}
              onUpdate={updateOpening}
              onRemove={removeFromRepertoire}
            />
          )}

          {/* Browse & Add Tab */}
          {activeTab === 'browse' && (
            <OpeningBrowser
              onAddToRepertoire={addToRepertoire}
              existingRepertoire={repertoire}
            />
          )}
        </Box>
      </AccordionDetails>
    </Accordion>
  );
}
