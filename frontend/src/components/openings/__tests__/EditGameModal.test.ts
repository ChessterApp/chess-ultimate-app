import { describe, it, expect } from 'vitest';
import type { UserGame } from '@/hooks/useUserGames';

/**
 * EditGameModal — Dirty-checking and form-to-update logic tests
 */

const sampleGame: UserGame = {
  id: 'game-1',
  user_id: 'user-1',
  title: 'My Game',
  white: 'Carlsen, Magnus',
  black: 'Nepomniachtchi, Ian',
  white_elo: 2855,
  black_elo: 2782,
  result: '1-0',
  date: '2021.12.03',
  event: 'World Championship',
  eco: 'D02',
  opening_name: "Queen's Pawn Game",
  pgn: '1. d4 Nf6 2. Nf3 d5 1-0',
  notes: 'Great game',
  tags: ['classical'],
  is_favorite: false,
  source: 'manual',
  created_at: '2024-01-01T00:00:00Z',
  updated_at: '2024-01-01T00:00:00Z',
};

interface GameFormData {
  title: string;
  white: string;
  black: string;
  whiteElo: string;
  blackElo: string;
  result: string;
  date: string;
  event: string;
  openingName: string;
  notes: string;
}

function gameToForm(game: UserGame): GameFormData {
  return {
    title: game.title || '',
    white: game.white || '',
    black: game.black || '',
    whiteElo: game.white_elo != null ? String(game.white_elo) : '',
    blackElo: game.black_elo != null ? String(game.black_elo) : '',
    result: game.result || '*',
    date: game.date || '',
    event: game.event || '',
    openingName: game.opening_name || '',
    notes: game.notes || '',
  };
}

function computeUpdates(initial: GameFormData, current: GameFormData): Record<string, unknown> {
  const updates: Record<string, unknown> = {};
  if (current.title !== initial.title) updates.title = current.title || null;
  if (current.white !== initial.white) updates.white = current.white;
  if (current.black !== initial.black) updates.black = current.black;
  if (current.whiteElo !== initial.whiteElo) updates.white_elo = current.whiteElo ? parseInt(current.whiteElo, 10) : null;
  if (current.blackElo !== initial.blackElo) updates.black_elo = current.blackElo ? parseInt(current.blackElo, 10) : null;
  if (current.result !== initial.result) updates.result = current.result;
  if (current.date !== initial.date) updates.date = current.date || null;
  if (current.event !== initial.event) updates.event = current.event || null;
  if (current.openingName !== initial.openingName) updates.opening_name = current.openingName || null;
  if (current.notes !== initial.notes) updates.notes = current.notes || null;
  return updates;
}

describe('EditGameModal — gameToForm', () => {
  it('should convert a full UserGame to form data', () => {
    const form = gameToForm(sampleGame);
    expect(form).toEqual({
      title: 'My Game',
      white: 'Carlsen, Magnus',
      black: 'Nepomniachtchi, Ian',
      whiteElo: '2855',
      blackElo: '2782',
      result: '1-0',
      date: '2021.12.03',
      event: 'World Championship',
      openingName: "Queen's Pawn Game",
      notes: 'Great game',
    });
  });

  it('should handle null/undefined fields gracefully', () => {
    const minimalGame: UserGame = {
      ...sampleGame,
      title: null,
      white_elo: null,
      black_elo: null,
      date: null,
      event: null,
      opening_name: null,
      notes: null,
    };
    const form = gameToForm(minimalGame);
    expect(form.title).toBe('');
    expect(form.whiteElo).toBe('');
    expect(form.blackElo).toBe('');
    expect(form.date).toBe('');
    expect(form.event).toBe('');
    expect(form.openingName).toBe('');
    expect(form.notes).toBe('');
  });
});

describe('EditGameModal — Dirty checking', () => {
  it('should return empty updates when nothing changed', () => {
    const form = gameToForm(sampleGame);
    const updates = computeUpdates(form, form);
    expect(Object.keys(updates)).toHaveLength(0);
  });

  it('should detect title change', () => {
    const initial = gameToForm(sampleGame);
    const current = { ...initial, title: 'Updated Title' };
    const updates = computeUpdates(initial, current);
    expect(updates).toEqual({ title: 'Updated Title' });
  });

  it('should detect player name changes', () => {
    const initial = gameToForm(sampleGame);
    const current = { ...initial, white: 'Kramnik', black: 'Kasparov' };
    const updates = computeUpdates(initial, current);
    expect(updates).toEqual({ white: 'Kramnik', black: 'Kasparov' });
  });

  it('should detect elo changes and convert to numbers', () => {
    const initial = gameToForm(sampleGame);
    const current = { ...initial, whiteElo: '2900', blackElo: '2800' };
    const updates = computeUpdates(initial, current);
    expect(updates).toEqual({ white_elo: 2900, black_elo: 2800 });
  });

  it('should set null when clearing elo', () => {
    const initial = gameToForm(sampleGame);
    const current = { ...initial, whiteElo: '' };
    const updates = computeUpdates(initial, current);
    expect(updates).toEqual({ white_elo: null });
  });

  it('should detect result change', () => {
    const initial = gameToForm(sampleGame);
    const current = { ...initial, result: '0-1' };
    const updates = computeUpdates(initial, current);
    expect(updates).toEqual({ result: '0-1' });
  });

  it('should set null when clearing optional text fields', () => {
    const initial = gameToForm(sampleGame);
    const current = { ...initial, date: '', event: '', notes: '', title: '' };
    const updates = computeUpdates(initial, current);
    expect(updates).toEqual({
      date: null,
      event: null,
      notes: null,
      title: null,
    });
  });

  it('should only include changed fields', () => {
    const initial = gameToForm(sampleGame);
    const current = { ...initial, white: 'New White', notes: 'New notes' };
    const updates = computeUpdates(initial, current);
    expect(Object.keys(updates)).toHaveLength(2);
    expect(updates.white).toBe('New White');
    expect(updates.notes).toBe('New notes');
    expect(updates).not.toHaveProperty('black');
    expect(updates).not.toHaveProperty('result');
  });
});
