/**
 * @vitest-environment jsdom
 *
 * GameReplayBoard is migrated from the legacy chessboard library to the shared
 * ChessgroundBoard wrapper (phase 5a). These tests stub ChessgroundBoard to
 * capture the props it receives, verifying the replay board stays view-only,
 * tracks the current FEN as you navigate, orients to the player's colour, and
 * highlights the last move that produced the shown position.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import React from 'react';
import { cleanup, render, fireEvent } from '@testing-library/react';

// Capture every props object ChessgroundBoard is rendered with.
const boardProps = vi.hoisted(() => [] as any[]);

vi.mock('@/components/chess/ChessgroundBoard', () => ({
  default: (props: any) => {
    boardProps.push(props);
    return <div data-testid="cg-board" data-fen={props.fen} />;
  },
}));

vi.mock('next-intl', () => ({
  useTranslations: () => (k: string) => k,
}));

vi.mock('@/hooks/useReplayStockfish', () => ({
  useReplayStockfish: () => ({
    evaluation: null,
    isAnalyzing: false,
    depth: 0,
    analyze: vi.fn(),
    stopAnalysis: vi.fn(),
  }),
}));

vi.mock('../ReplayEvalBar', () => ({ default: () => <div /> }));
vi.mock('../ReplayEngineLines', () => ({ default: () => <div /> }));

import GameReplayBoard from '../GameReplayBoard';

const START_FEN = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1';
const AFTER_E4 = 'rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1';

const gameInfo = {
  white_name: 'Alice',
  black_name: 'Bob',
  white_elo: 2000,
  black_elo: 1900,
  result: '1-0',
  date: '2024.01.01',
  event: 'Test Open',
  eco: 'C20',
};

function lastBoardProps() {
  return boardProps[boardProps.length - 1];
}

describe('GameReplayBoard → ChessgroundBoard migration', () => {
  beforeEach(() => {
    boardProps.length = 0;
  });

  afterEach(() => {
    cleanup();
  });

  it('renders a view-only board at the starting position', () => {
    render(
      <GameReplayBoard pgn="1. e4 e5 2. Nf3" gameInfo={gameInfo} playerName="Alice" onClose={vi.fn()} />
    );

    const props = lastBoardProps();
    expect(props.viewOnly).toBe(true);
    expect(props.movable).toBeFalsy();
    expect(props.fen).toBe(START_FEN);
    expect(props.lastMove).toBeNull();
  });

  it('orients to white when the player is the white side', () => {
    render(
      <GameReplayBoard pgn="1. e4 e5" gameInfo={gameInfo} playerName="Alice" onClose={vi.fn()} />
    );
    expect(lastBoardProps().orientation).toBe('white');
  });

  it('orients to black when the player is the black side', () => {
    render(
      <GameReplayBoard pgn="1. e4 e5" gameInfo={gameInfo} playerName="Bob" onClose={vi.fn()} />
    );
    expect(lastBoardProps().orientation).toBe('black');
  });

  it('advances the FEN and highlights the last move on next', () => {
    const { getByTitle } = render(
      <GameReplayBoard pgn="1. e4 e5" gameInfo={gameInfo} playerName="Alice" onClose={vi.fn()} />
    );

    fireEvent.click(getByTitle('Next (→)'));

    const props = lastBoardProps();
    expect(props.fen).toBe(AFTER_E4);
    expect(props.lastMove).toEqual(['e2', 'e4']);
  });
});
