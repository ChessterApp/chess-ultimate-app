'use client';

import React, { useState, useMemo, useEffect, useCallback } from 'react';
import { Box } from '@mui/material';
import { SvgIcon, SvgIconProps } from '@mui/material';
import { Chessboard } from 'react-chessboard';
import { Chess, Square } from 'chess.js';
import { useLocalStorage } from 'usehooks-ts';
import {
  BOARD_THEMES,
  getCurrentThemeColors,
  DEFAULT_BOARD_SHOW_COORDINATE,
} from '@/libs/setting/helper';
import type { Arrow, BoardOrientation } from 'react-chessboard/dist/chessboard/types';

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
  orientation: BoardOrientation;
  onMove: (from: string, to: string, piece: string, newFen: string, moveSan: string, moveUci: string) => void;
  customArrows?: Arrow[];
  onReset: () => void;
  onGoToStart: () => void;
  onPrev: () => void;
  onNext: () => void;
  onGoToEnd: () => void;
  onFlip: () => void;
}

// ─── Component ───

export default function DebutBoard({
  fen, orientation, onMove, customArrows,
  onReset, onGoToStart, onPrev, onNext, onGoToEnd, onFlip,
}: DebutBoardProps) {
  const [windowWidth, setWindowWidth] = useState(typeof window !== 'undefined' ? window.innerWidth : 1024);
  const [selectedSquare, setSelectedSquare] = useState<string | null>(null);
  const [legalMoves, setLegalMoves] = useState<string[]>([]);

  const [pieceType] = useLocalStorage<string>('board_piece_type', 'Fritz');
  const [boardTheme] = useLocalStorage<string>('board_theme', 'chessbase');
  const [showCoordinates] = useLocalStorage<boolean>('board_show_coordinates', DEFAULT_BOARD_SHOW_COORDINATE);
  const [animationDuration] = useLocalStorage<number>('board_ui_animation_duration', 300);

  const themeColors = useMemo(() => getCurrentThemeColors(boardTheme), [boardTheme]);

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

  // Piece images — map names to actual folder (filesystem is case-sensitive)
  const ASSET_VERSION = process.env.NEXT_PUBLIC_ASSET_VERSION || '';
  const customPieces = useMemo(() => {
    const folderMap: Record<string, string> = { cburnett: 'Cburnett', fritz: 'Fritz', Fritz: 'Fritz' };
    const folder = folderMap[pieceType] || pieceType || 'Fritz';
    const svgSets = ['cburnett', 'fritz'];
    const isSvg = svgSets.includes(pieceType.toLowerCase());
    const ext = isSvg ? 'svg' : 'png';
    const pieces: Record<string, any> = {};
    const pieceTypes = ['wP', 'wN', 'wB', 'wR', 'wQ', 'wK', 'bP', 'bN', 'bB', 'bR', 'bQ', 'bK'];
    pieceTypes.forEach(p => {
      pieces[p] = ({ squareWidth }: { squareWidth: number }) => (
        <img
          src={`/static/pieces/${folder}/${p}.${ext}?v=${ASSET_VERSION}`}
          alt={p}
          style={{ width: squareWidth, height: squareWidth }}
          onError={(e) => {
            const img = e.currentTarget;
            if (!img.dataset.retried) {
              img.dataset.retried = '1';
              img.src = `${img.src.split('?')[0]}?v=${ASSET_VERSION}&t=${Date.now()}`;
            }
          }}
        />
      );
    });
    return pieces;
  }, [pieceType, ASSET_VERSION]);

  // Legal move squares styling
  const moveSquares = useMemo(() => {
    const styles: Record<string, React.CSSProperties> = {};
    if (selectedSquare) {
      styles[selectedSquare] = {
        backgroundColor: themeColors.selectedSquareColor || 'rgba(255, 215, 0, 0.6)',
      };
    }
    legalMoves.forEach(sq => {
      styles[sq] = {
        background: `radial-gradient(circle, ${themeColors.squareClickLegalColor || 'rgba(86, 65, 6, 0.5)'} 25%, transparent 25%)`,
        borderRadius: '50%',
      };
    });
    return styles;
  }, [selectedSquare, legalMoves, themeColors]);

  // Handle square click for move selection
  const handleSquareClick = useCallback((square: Square) => {
    try {
      const game = new Chess(fen);

      // If we already have a selected square, try to make the move
      if (selectedSquare) {
        try {
          const move = game.move({ from: selectedSquare as Square, to: square, promotion: 'q' });
          if (move) {
            onMove(selectedSquare, square, move.piece, game.fen(), move.san, move.from + move.to);
            setSelectedSquare(null);
            setLegalMoves([]);
            return;
          }
        } catch {
          // Invalid move — fall through to select new piece
        }
      }

      // Select new piece
      const moves = game.moves({ square, verbose: true });
      if (moves.length > 0) {
        setSelectedSquare(square);
        setLegalMoves(moves.map(m => m.to));
      } else {
        setSelectedSquare(null);
        setLegalMoves([]);
      }
    } catch {
      setSelectedSquare(null);
      setLegalMoves([]);
    }
  }, [fen, selectedSquare, onMove]);

  // Handle drop
  const handleDrop = useCallback((sourceSquare: Square, targetSquare: Square, piece: string): boolean => {
    try {
      const game = new Chess(fen);
      const move = game.move({
        from: sourceSquare,
        to: targetSquare,
        promotion: piece[1]?.toLowerCase() === 'q' ? 'q' : 'q',
      });
      if (move) {
        onMove(sourceSquare, targetSquare, piece, game.fen(), move.san, move.from + move.to);
        setSelectedSquare(null);
        setLegalMoves([]);
        return true;
      }
    } catch { /* invalid move */ }
    return false;
  }, [fen, onMove]);

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
      <Chessboard
        id="debut-board"
        position={fen}
        boardOrientation={orientation}
        boardWidth={boardSize}
        onSquareClick={handleSquareClick}
        onPieceDrop={handleDrop}
        customBoardStyle={{
          borderRadius: '2px',
          boxShadow: '0 2px 10px rgba(0,0,0,0.5)',
        }}
        customDarkSquareStyle={{ backgroundColor: themeColors.darkSquareColor }}
        customLightSquareStyle={{ backgroundColor: themeColors.lightSquareColor }}
        customSquareStyles={moveSquares}
        customArrows={customArrows}
        customPieces={customPieces}
        showBoardNotation={showCoordinates}
        animationDuration={animationDuration}
      />

      {/* Board Control Bar — matches Analysis board exactly */}
      <Box
        sx={{
          display: 'flex',
          flexDirection: 'row',
          alignItems: 'center',
          backgroundColor: '#2a2a2a',
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
              color: '#a0a0a0',
              padding: '5px',
              transition: 'background-color 0.15s, color 0.15s',
              '&:hover': {
                backgroundColor: 'rgba(255,255,255,0.08)',
                color: '#fff',
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
