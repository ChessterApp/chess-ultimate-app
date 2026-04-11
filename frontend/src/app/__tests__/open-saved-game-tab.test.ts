import { describe, it, expect } from 'vitest';
import { parseGamePgn } from '@/components/openings/GameViewerPanel';
import type { OpenedGame } from '@/components/openings/GameViewerPanel';

/**
 * Open Saved Game as Tab — Integration Tests
 *
 * Tests the flow of opening a saved (user) game from My Games panel
 * as a new tab, verifying the game viewer works correctly.
 */

// Simulate the UserGame shape from useUserGames
interface UserGame {
  id: string;
  user_id: string;
  white: string;
  black: string;
  white_elo: number | null;
  black_elo: number | null;
  result: string;
  date: string | null;
  event: string | null;
  eco: string | null;
  opening_name: string | null;
  pgn: string;
  source: string;
  tags: string[];
  is_favorite: boolean;
}

const sampleUserGame: UserGame = {
  id: 'usr-game-abc',
  user_id: 'user_123',
  white: 'Fischer, Bobby',
  black: 'Spassky, Boris',
  white_elo: 2785,
  black_elo: 2660,
  result: '1-0',
  date: '1972.07.11',
  event: 'World Championship',
  eco: 'C95',
  opening_name: 'Ruy Lopez',
  pgn: '1. e4 e5 2. Nf3 Nc6 3. Bb5 a6 1-0',
  source: 'pgn_import',
  tags: ['favorite', 'classical'],
  is_favorite: true,
};

describe('Open Saved Game — UserGame to OpenedGame conversion', () => {
  // Replicate the handleOpenGame logic for UserGame → OpenedGame
  function convertUserGameToOpened(game: UserGame): OpenedGame {
    const parsed = parseGamePgn(game.pgn);
    return {
      id: String(game.id),
      white: game.white || '?',
      black: game.black || '?',
      whiteElo: game.white_elo ?? undefined,
      blackElo: game.black_elo ?? undefined,
      result: game.result || '*',
      eco: game.eco ?? undefined,
      date: game.date ?? undefined,
      event: game.event ?? undefined,
      pgn: game.pgn,
      moves: parsed.moves,
      fens: parsed.fens,
      startingFen: parsed.startingFen,
      source: game.user_id ? 'user' : (game.source || 'twic'),
    };
  }

  it('should convert a user game with all fields', () => {
    const opened = convertUserGameToOpened(sampleUserGame);
    expect(opened.id).toBe('usr-game-abc');
    expect(opened.white).toBe('Fischer, Bobby');
    expect(opened.black).toBe('Spassky, Boris');
    expect(opened.whiteElo).toBe(2785);
    expect(opened.blackElo).toBe(2660);
    expect(opened.result).toBe('1-0');
    expect(opened.eco).toBe('C95');
    expect(opened.date).toBe('1972.07.11');
    expect(opened.event).toBe('World Championship');
    expect(opened.source).toBe('user');
  });

  it('should parse PGN into moves and FENs', () => {
    const opened = convertUserGameToOpened(sampleUserGame);
    expect(opened.moves).toEqual(['e4', 'e5', 'Nf3', 'Nc6', 'Bb5', 'a6']);
    expect(opened.fens.length).toBe(6);
    expect(opened.startingFen).toBe('rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1');
  });

  it('should handle missing optional fields gracefully', () => {
    const minimalGame: UserGame = {
      id: 'usr-game-min',
      user_id: 'user_456',
      white: 'Me',
      black: 'Opponent',
      white_elo: null,
      black_elo: null,
      result: '*',
      date: null,
      event: null,
      eco: null,
      opening_name: null,
      pgn: '1. d4 d5 *',
      source: 'board_entry',
      tags: [],
      is_favorite: false,
    };
    const opened = convertUserGameToOpened(minimalGame);
    expect(opened.whiteElo).toBeUndefined();
    expect(opened.blackElo).toBeUndefined();
    expect(opened.date).toBeUndefined();
    expect(opened.event).toBeUndefined();
    expect(opened.eco).toBeUndefined();
    expect(opened.moves).toEqual(['d4', 'd5']);
  });

  it('should set source to "user" for games with user_id', () => {
    const opened = convertUserGameToOpened(sampleUserGame);
    expect(opened.source).toBe('user');
  });
});

describe('Open Saved Game — Tab state management', () => {
  function simulateOpenGame(
    openedGames: OpenedGame[],
    activeTab: string,
    newGame: OpenedGame
  ): { openedGames: OpenedGame[]; activeTab: string; moveIndices: Record<string, number> } {
    const existing = openedGames.find(g => g.id === newGame.id);
    if (existing) {
      return { openedGames, activeTab: newGame.id, moveIndices: {} };
    }
    return {
      openedGames: [...openedGames, newGame],
      activeTab: newGame.id,
      moveIndices: { [newGame.id]: -1 },
    };
  }

  const testGame: OpenedGame = {
    id: 'usr-game-1',
    white: 'Player A',
    black: 'Player B',
    result: '1-0',
    pgn: '1. e4 e5 1-0',
    moves: ['e4', 'e5'],
    fens: ['fen1', 'fen2'],
    startingFen: 'start',
    source: 'user',
  };

  it('should add game to opened games list', () => {
    const result = simulateOpenGame([], 'my-games', testGame);
    expect(result.openedGames).toHaveLength(1);
    expect(result.openedGames[0].id).toBe('usr-game-1');
  });

  it('should set active tab to the game id', () => {
    const result = simulateOpenGame([], 'my-games', testGame);
    expect(result.activeTab).toBe('usr-game-1');
  });

  it('should initialize move index to -1 (starting position)', () => {
    const result = simulateOpenGame([], 'my-games', testGame);
    expect(result.moveIndices['usr-game-1']).toBe(-1);
  });

  it('should switch to existing tab if game already open', () => {
    const result = simulateOpenGame([testGame], 'debut', testGame);
    expect(result.openedGames).toHaveLength(1); // Not duplicated
    expect(result.activeTab).toBe('usr-game-1');
  });
});

describe('Open Saved Game — Board FEN calculation', () => {
  function getActiveGameFen(
    activeGame: OpenedGame | undefined,
    moveIndex: number
  ): string | null {
    if (!activeGame) return null;
    if (moveIndex === -1) return activeGame.startingFen;
    return activeGame.fens[moveIndex] || activeGame.startingFen;
  }

  const parsed = parseGamePgn('1. e4 e5 2. Nf3 Nc6 1/2-1/2');
  const game: OpenedGame = {
    id: 'test',
    white: 'A',
    black: 'B',
    result: '1/2-1/2',
    pgn: '1. e4 e5 2. Nf3 Nc6 1/2-1/2',
    moves: parsed.moves,
    fens: parsed.fens,
    startingFen: parsed.startingFen,
    source: 'user',
  };

  it('should show starting position at move index -1', () => {
    const fen = getActiveGameFen(game, -1);
    expect(fen).toBe('rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1');
  });

  it('should show position after first move (e4) at index 0', () => {
    const fen = getActiveGameFen(game, 0);
    expect(fen).toContain('rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR');
  });

  it('should show position after e4 e5 at index 1', () => {
    const fen = getActiveGameFen(game, 1);
    expect(fen).toContain('rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR');
  });

  it('should show last position at final move index', () => {
    const fen = getActiveGameFen(game, game.moves.length - 1);
    expect(fen).toBeTruthy();
    expect(fen).not.toBe(game.startingFen);
  });

  it('should return null when no active game', () => {
    const fen = getActiveGameFen(undefined, -1);
    expect(fen).toBeNull();
  });

  it('should fallback to starting FEN for out-of-bounds index', () => {
    const fen = getActiveGameFen(game, 999);
    expect(fen).toBe(game.startingFen);
  });
});

describe('Open Saved Game — Game viewer right panel routing', () => {
  type RightPanelContent = 'repertoire' | 'my-games' | 'game-viewer' | 'none';

  function getRightPanelContent(
    activeTab: string,
    hasActiveGame: boolean,
    isLargeScreen: boolean
  ): RightPanelContent {
    if (activeTab === 'debut') return 'repertoire';
    if (activeTab === 'my-games') return 'my-games';
    if (hasActiveGame && isLargeScreen) return 'game-viewer';
    if (hasActiveGame && !isLargeScreen) return 'none'; // hidden on xs, shown below board instead
    return 'none';
  }

  it('should show game-viewer in right panel on large screens', () => {
    expect(getRightPanelContent('usr-game-1', true, true)).toBe('game-viewer');
  });

  it('should hide game-viewer in right panel on small screens', () => {
    expect(getRightPanelContent('usr-game-1', true, false)).toBe('none');
  });

  it('should show my-games panel when on my-games tab', () => {
    expect(getRightPanelContent('my-games', false, true)).toBe('my-games');
  });

  it('should show repertoire when on debut tab', () => {
    expect(getRightPanelContent('debut', false, true)).toBe('repertoire');
  });
});

describe('Open Saved Game — Move navigation', () => {
  function navigateMove(
    currentIndex: number,
    totalMoves: number,
    action: 'prev' | 'next' | 'start' | 'end'
  ): number {
    switch (action) {
      case 'prev': return Math.max(-1, currentIndex - 1);
      case 'next': return Math.min(totalMoves - 1, currentIndex + 1);
      case 'start': return -1;
      case 'end': return totalMoves - 1;
    }
  }

  it('should go to starting position on "start"', () => {
    expect(navigateMove(3, 10, 'start')).toBe(-1);
  });

  it('should go to last move on "end"', () => {
    expect(navigateMove(3, 10, 'end')).toBe(9);
  });

  it('should not go before starting position', () => {
    expect(navigateMove(-1, 10, 'prev')).toBe(-1);
  });

  it('should not go past last move', () => {
    expect(navigateMove(9, 10, 'next')).toBe(9);
  });

  it('should move forward one step', () => {
    expect(navigateMove(3, 10, 'next')).toBe(4);
  });

  it('should move backward one step', () => {
    expect(navigateMove(3, 10, 'prev')).toBe(2);
  });

  it('should move from starting position to first move', () => {
    expect(navigateMove(-1, 10, 'next')).toBe(0);
  });
});

describe('parseGamePgn — PGN parsing for saved games', () => {
  it('should parse a standard PGN with headers', () => {
    const pgn = `[White "Fischer"]
[Black "Spassky"]
[Result "1-0"]

1. e4 e5 2. Nf3 Nc6 3. Bb5 a6 1-0`;
    const result = parseGamePgn(pgn);
    expect(result.moves).toEqual(['e4', 'e5', 'Nf3', 'Nc6', 'Bb5', 'a6']);
    expect(result.fens.length).toBe(6);
  });

  it('should parse a PGN without headers', () => {
    const pgn = '1. d4 d5 2. c4 e6 *';
    const result = parseGamePgn(pgn);
    expect(result.moves).toEqual(['d4', 'd5', 'c4', 'e6']);
    expect(result.fens.length).toBe(4);
  });

  it('should return correct starting FEN', () => {
    const result = parseGamePgn('1. e4 *');
    expect(result.startingFen).toBe('rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1');
  });

  it('should handle empty PGN gracefully', () => {
    const result = parseGamePgn('');
    expect(result.moves).toEqual([]);
    expect(result.fens).toEqual([]);
  });

  it('should produce FENs that match move count', () => {
    const pgn = '1. e4 e5 2. Nf3 Nc6 3. Bb5 a6 4. Ba4 Nf6 *';
    const result = parseGamePgn(pgn);
    expect(result.fens.length).toBe(result.moves.length);
  });
});

describe('Source badge mapping for user games', () => {
  const SOURCE_LABELS: Record<string, string> = {
    twic: 'Master Games',
    lichess: 'Lichess',
    chesscom: 'Chess.com',
    pgn: 'PGN',
    user: 'My Game',
    internal: 'Internal',
    pgn_import: 'My Game',
    board_entry: 'My Game',
    scoresheet: 'My Game',
    manual: 'My Game',
    database: 'Saved',
  };

  function getSourceLabel(source: string): string {
    return SOURCE_LABELS[source.toLowerCase()] || source;
  }

  it('should label user source as "My Game"', () => {
    expect(getSourceLabel('user')).toBe('My Game');
  });

  it('should label pgn_import as "My Game"', () => {
    expect(getSourceLabel('pgn_import')).toBe('My Game');
  });

  it('should label board_entry as "My Game"', () => {
    expect(getSourceLabel('board_entry')).toBe('My Game');
  });

  it('should label scoresheet as "My Game"', () => {
    expect(getSourceLabel('scoresheet')).toBe('My Game');
  });

  it('should label database source as "Saved"', () => {
    expect(getSourceLabel('database')).toBe('Saved');
  });

  it('should label twic as "Master Games"', () => {
    expect(getSourceLabel('twic')).toBe('Master Games');
  });

  it('should fall back to raw string for unknown sources', () => {
    expect(getSourceLabel('unknown_source')).toBe('unknown_source');
  });
});
