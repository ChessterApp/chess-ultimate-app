'use client';

import React, { useState, useMemo, useEffect, useCallback } from 'react';
import { Box } from '@mui/material';
import ChessgroundBoard from '@/components/chess/ChessgroundBoard';
import {
  CBResetIcon,
  CBGoToStartIcon,
  CBPreviousMoveIcon,
  CBNextMoveIcon,
  CBGoToEndIcon,
  CBFlipBoardIcon,
} from '@/components/icons/ChessBaseNavIcons';
import { Chess, Square } from 'chess.js';
import { useLocalStorage } from 'usehooks-ts';
import type { Key } from 'chessground/types';
import {
  BOARD_THEMES,
  getCurrentThemeColors,
  DEFAULT_BOARD_SHOW_COORDINATE,
  DEFAULT_BOARD_ANIMATION_DURATION,
} from '@/lib/setting/helper';

// ─── Types ───

interface DebutBoardProps {
  fen: string;
  orientation: 'white' | 'black';
  onMove: (from: string, to: string, piece: string, newFen: string, moveSan: string, moveUci: string) => void;
  customArrows?: Array<{ from: Key; to: Key; brush: string }>;
  onReset: () => void;
  onGoToStart: () => void;
  onPrev: () => void;
  onNext: () => void;
  onGoToEnd: () => void;
  onFlip: () => void;
}

// ─── Component ───

export default function DebutBoard({
  fen, orientation, onMove, customArrows = [],
  onReset, onGoToStart, onPrev, onNext, onGoToEnd, onFlip,
}: DebutBoardProps) {
  const [windowWidth, setWindowWidth] = useState(typeof window !== 'undefined' ? window.innerWidth : 1024);

  const [showCoordinates] = useLocalStorage<boolean>('board_show_coordinates', DEFAULT_BOARD_SHOW_COORDINATE);
  const [animationDuration] = useLocalStorage<number>('board_ui_animation_duration', DEFAULT_BOARD_ANIMATION_DURATION);

  // Responsive board size
  useEffect(() => {
    const handleResize = () => setWindowWidth(window.innerWidth);
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  const boardSize = useMemo(() => {
    if (windowWidth < 400) return Math.min(windowWidth - 32, 320);
    if (windowWidth < 600) return Math.min(windowWidth - 24, 360);
    if (windowWidth < 768) return Math.min(windowWidth - 32, 420);
    if (windowWidth < 1024) return Math.min(windowWidth - 48, 480);
    return 520;
  }, [windowWidth]);

  // Handle chessground move
  const handleMove = useCallback((from: Key, to: Key, promotion?: 'q' | 'r' | 'b' | 'n') => {
    try {
      const game = new Chess(fen);
      const move = game.move({
        from,
        to,
        promotion: promotion ?? 'q', // Board picks the piece; queen by default.
      });
      if (move) {
        onMove(from, to, move.piece, game.fen(), move.san, move.from + move.to);
      }
    } catch (err) {
      console.error('Invalid move:', err);
    }
  }, [fen, onMove]);

  return (
    <Box
      sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center' }}
      style={{ ['--cg-animation-duration' as any]: `${animationDuration}ms` }}
    >
      <ChessgroundBoard
        fen={fen}
        orientation={orientation}
        boardSize={boardSize}
        onMove={handleMove}
        arrows={customArrows}
        showCoordinates={showCoordinates}
        animationDuration={animationDuration}
        movable={true}
      />

      {/* Board Control Bar — matches Analysis board exactly */}
      <Box
        sx={{
          display: 'flex',
          flexDirection: 'row',
          alignItems: 'center',
          backgroundColor: 'rgba(255,255,255,0.95)',
          borderRadius: 0,
          height: 38,
          width: boardSize,
          overflow: 'hidden',
        }}
      >
        {[
          { icon: <CBResetIcon sx={{ width: 22, height: 22 }} />, onClick: onReset, title: 'Reset board', flex: 1 },
          { icon: <CBGoToStartIcon sx={{ width: 18, height: 14 }} />, onClick: onGoToStart, title: 'Go to start', flex: 1 },
          { icon: <CBPreviousMoveIcon sx={{ width: 14, height: 15 }} />, onClick: onPrev, title: 'Previous move', flex: 1.42 },
          { icon: <CBNextMoveIcon sx={{ width: 14, height: 15 }} />, onClick: onNext, title: 'Next move', flex: 1.42 },
          { icon: <CBGoToEndIcon sx={{ width: 18, height: 14 }} />, onClick: onGoToEnd, title: 'Go to end', flex: 1 },
          { icon: <CBFlipBoardIcon sx={{ width: 26, height: 22 }} />, onClick: onFlip, title: 'Flip board', flex: 1 },
        ].map((btn, i) => (
          <Box
            key={i}
            onClick={btn.onClick}
            title={btn.title}
            sx={{
              flex: btn.flex,
              height: 38,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              cursor: 'pointer',
              userSelect: 'none',
              color: 'text.secondary',
              padding: '5px',
              transition: 'background-color 0.15s, color 0.15s',
              '&:hover': {
                backgroundColor: 'rgba(31,41,55,0.06)',
                color: 'text.primary',
              },
            }}
          >
            {btn.icon}
          </Box>
        ))}
      </Box>
    </Box>
  );
}
