/**
 * @vitest-environment jsdom
 *
 * GameReplayBoard is migrated from the legacy chessboard library to the shared
 * ChessgroundBoard wrapper (phase 5a). These tests stub ChessgroundBoard to
 * capture the props it receives, verifying the replay board stays view-only,
 * tracks the current FEN as you navigate, orients to the player's colour, and
 * highlights the last move that produced the shown position. The engine panel
 * is off by default and follows the shared depth/lines display settings.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import React from 'react';
import { cleanup, render, fireEvent, screen, within } from '@testing-library/react';

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

const engineOpts = vi.hoisted(() => [] as any[]);
const analyze = vi.hoisted(() => vi.fn());
const ENGINE_LINES = [
  { pv: ['e7e5', 'g1f3', 'b8c6', 'f1b5', 'a7a6', 'b5a4', 'g8f6', 'e1g1', 'f8e7'], cp: 30, depth: 16 },
  { pv: ['c7c5'], cp: 40, depth: 16 },
  { pv: ['e7e6'], cp: 45, depth: 16 },
];
vi.mock('@/hooks/useReplayStockfish', () => ({
  useReplayStockfish: (opts: any) => {
    engineOpts.push(opts);
    return {
      evaluation: opts.enabled ? { lines: ENGINE_LINES } : null,
      isAnalyzing: false,
      isReady: opts.enabled,
      depth: opts.enabled ? 16 : 0,
      engineName: opts.enabled ? 'sf17.1' : null,
      analyze,
      stopAnalysis: vi.fn(),
    };
  },
}));

vi.mock('../ReplayEvalBar', () => ({ default: () => <div /> }));

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
    engineOpts.length = 0;
    analyze.mockReset();
    window.localStorage.clear();
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

describe('GameReplayBoard engine panel', () => {
  const engineSwitch = () => screen.getByRole('switch', { hidden: true }) as HTMLInputElement;
  const lastOpts = () => engineOpts[engineOpts.length - 1];

  beforeEach(() => {
    engineOpts.length = 0;
    analyze.mockReset();
    window.localStorage.clear();
  });

  afterEach(() => {
    cleanup();
  });

  it('is off by default: no lines, no analysis', () => {
    render(<GameReplayBoard pgn="1. e4 e5" gameInfo={gameInfo} playerName="Alice" onClose={vi.fn()} />);
    expect(engineSwitch().checked).toBe(false);
    expect(lastOpts().enabled).toBe(false);
    expect(screen.queryByTestId('replay-engine-lines')).toBeNull();
    expect(analyze).not.toHaveBeenCalled();
  });

  it('when enabled shows one numbered line (default) with no "Engine Analysis"/"Depth" header', () => {
    render(<GameReplayBoard pgn="1. e4 e5" gameInfo={gameInfo} playerName="Alice" onClose={vi.fn()} />);
    fireEvent.click(engineSwitch());
    fireEvent.click(screen.getByTitle('Next (→)'));

    expect(lastOpts()).toEqual(expect.objectContaining({ enabled: true, depth: 18, multiPv: 1 }));
    expect(analyze).toHaveBeenLastCalledWith(AFTER_E4);
    expect(screen.getAllByTestId('engine-line-row')).toHaveLength(1);
    expect(screen.getByTestId('engine-line-moves').textContent).toBe('1…e5 2.Nf3 Nc6 3.Bb5 a6 4.Ba4 Nf6 5.O-O');
    expect(screen.queryByText(/engine analysis/i)).toBeNull();
    expect(screen.queryByText(/depth/i)).toBeNull();
    expect(screen.getByText('Stockfish 17.1')).toBeTruthy();
    expect(screen.getByText('· d16')).toBeTruthy();
  });

  it('follows the stored Lines setting', () => {
    window.localStorage.setItem('chesster.engineDisplay.v1', JSON.stringify({ depth: 12, lines: 3 }));
    render(<GameReplayBoard pgn="1. e4 e5" gameInfo={gameInfo} playerName="Alice" onClose={vi.fn()} />);
    fireEvent.click(engineSwitch());
    expect(lastOpts()).toEqual(expect.objectContaining({ depth: 12, multiPv: 3 }));
    expect(screen.getAllByTestId('engine-line-row')).toHaveLength(3);
  });

  it('puts the gear right after the engine label and opening it leaves the engine as is', () => {
    render(<GameReplayBoard pgn="1. e4 e5" gameInfo={gameInfo} playerName="Alice" onClose={vi.fn()} />);
    const label = screen.getByText('Stockfish');
    const gear = screen.getByRole('button', { name: 'settings' });
    expect(label.nextElementSibling).toBe(gear);

    fireEvent.click(gear);
    expect(engineSwitch().checked).toBe(false);
    fireEvent.click(within(screen.getByRole('group', { name: 'lines' })).getByRole('button', { name: '2' }));
    expect(engineSwitch().checked).toBe(false);
    expect(lastOpts()).toEqual(expect.objectContaining({ multiPv: 2 }));
  });
});
