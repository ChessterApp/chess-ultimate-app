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
      {/* Tab headers */}
      <Tabs
        value={activeTab}
        onChange={(_, val) => onTabChange(val)}
        sx={{
          minHeight: 36,
          borderBottom: '1px solid var(--border-subtle, rgba(255,255,255,0.08))',
          '& .MuiTab-root': {
            minHeight: 36,
            fontSize: 12,
            fontWeight: 600,
            textTransform: 'none',
            color: 'text.secondary',
            px: 2,
            py: 0.75,
            '&.Mui-selected': {
              color: '#14b8a6',
            },
          },
          '& .MuiTabs-indicator': {
            bgcolor: '#14b8a6',
            height: 2,
          },
        }}
      >
        <Tab label="TWIC" value="twic" />
        <Tab label="Lichess" value="lichess" />
        <Tab label="Chess.com" value="chesscom" />
      </Tabs>

      {/* Tab content */}
      <Box sx={{ flex: 1, overflow: 'auto', px: 1.5 }}>
        {activeTab === 'twic' && twicContent}
        {activeTab === 'lichess' && lichessContent}
        {activeTab === 'chesscom' && (chesscomContent || (
          <Box sx={{ py: 2, textAlign: 'center' }}>
            <Box sx={{ color: 'text.secondary', fontSize: 12, fontStyle: 'italic' }}>
              Chess.com player search coming soon
            </Box>
          </Box>
        ))}
      </Box>
    </Box>
  );
}
