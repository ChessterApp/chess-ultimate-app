'use client';

import React, { useState, useMemo, useEffect, useCallback } from 'react';
import { Box } from '@mui/material';
import { SvgIcon, SvgIconProps } from '@mui/material';
import ChessgroundBoard from '@/components/chess/ChessgroundBoard';
import { Chess, Square } from 'chess.js';
import { useLocalStorage } from 'usehooks-ts';
import type { Key } from 'chessground/types';
import {
  BOARD_THEMES,
  getCurrentThemeColors,
  DEFAULT_BOARD_SHOW_COORDINATE,
  DEFAULT_BOARD_ANIMATION_DURATION,
} from '@/libs/setting/helper';

// ─── ChessBase-style SVG icons ───

const CBResetIcon = (props: SvgIconProps) => (
  <SvgIcon {...props} viewBox="0 0 187.862 164">
    <path d="M82,135.848c-29.738,0-53.848-24.109-53.848-53.848S52.262,28.152,82,28.152c9.961,0,19.283,2.715,27.286,7.431 l14.266-24.269C111.364,4.135,97.168,0,82,0C36.713,0,0,36.713,0,82s36.713,82,82,82s82-36.713,82-82h-28.152 C135.848,111.738,111.738,135.848,82,135.848z" />
    <polygon points="111.124,82.652 149.493,16.195 187.862,82.652" />
  </SvgIcon>
);

const CBGoToStartIcon = (props: SvgIconProps) => (
  <SvgIcon {...props} viewBox="0 0 274.446 170">
    <path d="M274.446,150c0,11-7.794,15.5-17.32,10L144.543,95c-9.526-5.5-9.526-14.5,0-20l112.582-65c9.526-5.5,17.32-1,17.32,10V150z" />
    <path d="M147.223,150c0,11-7.794,15.5-17.32,10L17.32,95c-9.526-5.5-9.526-14.5,0-20l112.583-65c9.526-5.5,17.32-1,17.32,10V150z" />
    <path d="M28,10c0-5.5-4.5-10-10-10h-8C4.5,0,0,4.5,0,10v150c0,5.5,4.5,10,10,10h8c5.5,0,10-4.5,10-10V10z" />
  </SvgIcon>
);

const CBPreviousMoveIcon = (props: SvgIconProps) => (
  <SvgIcon {...props} viewBox="0 0 137.047 154.695">
    <path d="M137.047,142.347c0,11-7.794,15.5-17.32,10l-112.583-65c-9.526-5.5-9.526-14.5,0-20l112.583-65c9.526-5.5,17.32-1,17.32,10 V142.347z" />
  </SvgIcon>
);

const CBNextMoveIcon = (props: SvgIconProps) => (
  <SvgIcon {...props} viewBox="0 0 137.047 154.695">
    <path d="M0,12.347c0-11,7.794-15.5,17.32-10l112.583,65c9.526,5.5,9.526,14.5,0,20l-112.583,65c-9.526,5.5-17.32,1-17.32-10V12.347z" />
  </SvgIcon>
);

const CBGoToEndIcon = (props: SvgIconProps) => (
  <SvgIcon {...props} viewBox="0 0 274.446 170">
    <path d="M0,20C0,9,7.794,4.5,17.32,10l112.583,65c9.526,5.5,9.526,14.5,0,20L17.32,160C7.794,165.5,0,161,0,150V20z" />
    <path d="M127.223,20c0-11,7.794-15.5,17.32-10l112.582,65c9.526,5.5,9.526,14.5,0,20l-112.582,65c-9.526,5.5-17.32,1-17.32-10V20z" />
    <path d="M246.446,160c0,5.5,4.5,10,10,10h8c5.5,0,10-4.5,10-10V10c0-5.5-4.5-10-10-10h-8c-5.5,0-10,4.5-10,10V160z" />
  </SvgIcon>
);

const CBFlipBoardIcon = (props: SvgIconProps) => (
  <SvgIcon {...props} viewBox="0 0 303.866 170">
    <path d="M274.076,77.414c0-25.335-20.364-45.872-45.485-45.872V0c41.568,1.208,74.902,35.367,74.902,77.362 c0,41.993-33.334,76.154-74.902,77.362v-31.438C253.711,123.285,274.076,102.748,274.076,77.414z" />
    <polygon points="176.938,139.509 229.621,109.018 229.621,170" />
    <path d="M169.956,0v170H0.374V0H169.956z M22.818,147.5h62.346V85h62.346V22.5H85.165V85H22.818V147.5z" />
  </SvgIcon>
);

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
  const handleMove = useCallback((from: Key, to: Key) => {
    try {
      const game = new Chess(fen);
      const move = game.move({
        from,
        to,
        promotion: 'q', // Auto-queen promotion for simplicity
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
