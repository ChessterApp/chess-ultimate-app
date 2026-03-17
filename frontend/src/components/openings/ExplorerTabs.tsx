/**
 * ExplorerTabs — Tab container for TWIC | Lichess | Chess.com game sources
 */

'use client';

import React from 'react';
import { Box, Tab, Tabs } from '@mui/material';

export type ExplorerTab = 'twic' | 'lichess' | 'chesscom';

interface ExplorerTabsProps {
  activeTab: ExplorerTab;
  onTabChange: (tab: ExplorerTab) => void;
  twicContent: React.ReactNode;
  lichessContent: React.ReactNode;
  chesscomContent?: React.ReactNode;
}

export default function ExplorerTabs({
  activeTab,
  onTabChange,
  twicContent,
  lichessContent,
  chesscomContent,
}: ExplorerTabsProps) {
  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      {/* Tab headers - responsive horizontal scroll on mobile */}
      <Box
        sx={{
          borderBottom: '1px solid var(--border-subtle, rgba(255,255,255,0.08))',
          overflowX: 'auto',
          overflowY: 'hidden',
          // Hide scrollbar but keep functionality
          scrollbarWidth: 'none',
          '&::-webkit-scrollbar': { display: 'none' },
          // Smooth scroll on mobile
          WebkitOverflowScrolling: 'touch',
        }}
      >
        <Tabs
          value={activeTab}
          onChange={(_, val) => onTabChange(val)}
          variant="scrollable"
          scrollButtons={false}
          sx={{
            minHeight: { xs: 40, sm: 36 },
            '& .MuiTabs-flexContainer': {
              gap: { xs: 0.5, sm: 0 },
            },
            '& .MuiTab-root': {
              minHeight: { xs: 40, sm: 36 },
              fontSize: { xs: 11, sm: 12 },
              fontWeight: 600,
              textTransform: 'none',
              color: 'text.secondary',
              px: { xs: 1.5, sm: 2 },
              py: { xs: 0.5, sm: 0.75 },
              minWidth: { xs: 'auto', sm: 90 },
              borderRadius: { xs: '16px', sm: 0 },
              bgcolor: { xs: 'rgba(255,255,255,0.05)', sm: 'transparent' },
              mx: { xs: 0, sm: 0 },
              '&.Mui-selected': {
                color: '#fff',
                bgcolor: '#14b8a6',
                borderRadius: '16px',
                '&:hover': { bgcolor: '#0d9488' },
              },
              '&:hover': {
                bgcolor: { xs: 'rgba(255,255,255,0.08)', sm: 'transparent' },
              },
            },
            '& .MuiTabs-indicator': {
              bgcolor: '#14b8a6',
              height: 2,
              display: { xs: 'none', sm: 'block' },
            },
          }}
        >
          <Tab label="TWIC" value="twic" />
          <Tab label="Lichess" value="lichess" />
          <Tab label="Chess.com" value="chesscom" />
        </Tabs>
      </Box>

      {/* Tab content */}
      <Box sx={{ flex: 1, overflow: 'auto', px: { xs: 1, sm: 1.5 } }}>
        {activeTab === 'twic' && twicContent}
        {activeTab === 'lichess' && lichessContent}
        {activeTab === 'chesscom' && chesscomContent}
      </Box>
    </Box>
  );
}
