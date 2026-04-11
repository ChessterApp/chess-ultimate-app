import { describe, it, expect } from 'vitest';
import type { OpenedGame } from '../GameViewerPanel';

/**
 * GameViewerPanel — Save to My Games bookmark button logic tests
 */

const sampleGame: OpenedGame = {
  id: 'game-1',
  white: 'Carlsen, Magnus',
  black: 'Nepomniachtchi, Ian',
  whiteElo: 2855,
  blackElo: 2782,
  result: '1-0',
  eco: 'D02',
  date: '2021.12.03',
  event: 'World Championship',
  pgn: '1. d4 Nf6 2. Nf3 d5 3. g3 e6 1-0',
  moves: ['d4', 'Nf6', 'Nf3', 'd5', 'g3', 'e6'],
  fens: [],
  startingFen: 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1',
  source: 'twic',
};

describe('Save to My Games — Metadata extraction', () => {
  function extractSaveMetadata(game: OpenedGame) {
    return {
      white: game.white,
      black: game.black,
      white_elo: game.whiteElo ?? null,
      black_elo: game.blackElo ?? null,
      result: game.result,
      date: game.date ?? null,
      event: game.event ?? null,
      eco: game.eco ?? null,
      source: typeof game.source === 'string' ? game.source : 'database',
    };
  }

  it('should extract all metadata from a full game', () => {
    const meta = extractSaveMetadata(sampleGame);
    expect(meta).toEqual({
      white: 'Carlsen, Magnus',
      black: 'Nepomniachtchi, Ian',
      white_elo: 2855,
      black_elo: 2782,
      result: '1-0',
      date: '2021.12.03',
      event: 'World Championship',
      eco: 'D02',
      source: 'twic',
    });
  });

  it('should set null for missing optional fields', () => {
    const minimalGame: OpenedGame = {
      id: 'game-2',
      white: 'Player A',
      black: 'Player B',
      result: '*',
      pgn: '1. e4 *',
      moves: ['e4'],
      fens: [],
      startingFen: 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1',
    };
    const meta = extractSaveMetadata(minimalGame);
    expect(meta.white_elo).toBeNull();
    expect(meta.black_elo).toBeNull();
    expect(meta.date).toBeNull();
    expect(meta.event).toBeNull();
    expect(meta.eco).toBeNull();
  });

  it('should default source to "database" when source is not a string', () => {
    const gameWithNonStringSource: OpenedGame = {
      ...sampleGame,
      source: undefined,
    };
    const meta = extractSaveMetadata(gameWithNonStringSource);
    expect(meta.source).toBe('database');
  });

  it('should preserve string source value', () => {
    const meta = extractSaveMetadata(sampleGame);
    expect(meta.source).toBe('twic');
  });
});

describe('Save to My Games — Saved state tracking', () => {
  it('should track saved game IDs in a Set', () => {
    const savedGameIds = new Set<string>();
    expect(savedGameIds.has('game-1')).toBe(false);

    savedGameIds.add('game-1');
    expect(savedGameIds.has('game-1')).toBe(true);
    expect(savedGameIds.has('game-2')).toBe(false);
  });

  it('should not duplicate entries when saving the same game twice', () => {
    const savedGameIds = new Set<string>();
    savedGameIds.add('game-1');
    savedGameIds.add('game-1');
    expect(savedGameIds.size).toBe(1);
  });

  it('should track multiple saved games independently', () => {
    const savedGameIds = new Set<string>();
    savedGameIds.add('game-1');
    savedGameIds.add('game-2');
    expect(savedGameIds.size).toBe(2);
    expect(savedGameIds.has('game-1')).toBe(true);
    expect(savedGameIds.has('game-2')).toBe(true);
  });
});

describe('Save to My Games — Button state logic', () => {
  function getButtonState(
    onSaveToMyGames: boolean,
    saving: boolean,
    saved: boolean
  ): { visible: boolean; disabled: boolean; icon: 'loading' | 'saved' | 'unsaved' } {
    const visible = onSaveToMyGames;
    const disabled = saving || saved;
    const icon = saving ? 'loading' : saved ? 'saved' : 'unsaved';
    return { visible, disabled, icon };
  }

  it('should be hidden when onSaveToMyGames is not provided', () => {
    const state = getButtonState(false, false, false);
    expect(state.visible).toBe(false);
  });

  it('should be visible and enabled when not saved and not saving', () => {
    const state = getButtonState(true, false, false);
    expect(state.visible).toBe(true);
    expect(state.disabled).toBe(false);
    expect(state.icon).toBe('unsaved');
  });

  it('should be disabled and show loading during save', () => {
    const state = getButtonState(true, true, false);
    expect(state.disabled).toBe(true);
    expect(state.icon).toBe('loading');
  });

  it('should be disabled and show saved icon after successful save', () => {
    const state = getButtonState(true, false, true);
    expect(state.disabled).toBe(true);
    expect(state.icon).toBe('saved');
  });

  it('should show loading even if also marked saved (edge case)', () => {
    const state = getButtonState(true, true, true);
    expect(state.disabled).toBe(true);
    expect(state.icon).toBe('loading');
  });
});
