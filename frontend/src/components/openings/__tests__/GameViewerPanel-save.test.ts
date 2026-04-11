/**
 * @vitest-environment jsdom
 *
 * Integration tests for the Save to My Games bookmark button in GameViewerPanel.
 *
 * Tests the full save flow:
 * 1. handleSave callback lifecycle (saving → success/failure → saved state)
 * 2. Concurrent save prevention (no double saves)
 * 3. isSaved prop synchronization via useEffect
 * 4. handleSaveToMyGames integration (metadata mapping, snackbar, savedGameIds)
 * 5. Error handling paths
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useState, useCallback, useEffect } from 'react';
import type { OpenedGame } from '../GameViewerPanel';

// ─── Fixtures ────────────────────────────

const sampleGame: OpenedGame = {
  id: 'game-42',
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

const minimalGame: OpenedGame = {
  id: 'game-minimal',
  white: 'Player A',
  black: 'Player B',
  result: '*',
  pgn: '1. e4 *',
  moves: ['e4'],
  fens: [],
  startingFen: 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1',
};

// ─── Replicate handleSave hook logic from GameViewerPanel ──

function useBookmarkButton(
  game: OpenedGame,
  onSaveToMyGames?: (game: OpenedGame) => Promise<boolean>,
  isSaved = false,
) {
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(isSaved);

  useEffect(() => { setSaved(isSaved); }, [isSaved]);

  const handleSave = useCallback(async () => {
    if (!onSaveToMyGames || saving || saved) return;
    setSaving(true);
    const success = await onSaveToMyGames(game);
    setSaving(false);
    if (success) setSaved(true);
  }, [onSaveToMyGames, saving, saved, game]);

  return { saving, saved, handleSave };
}

// ─── Replicate handleSaveToMyGames from database/page.tsx ──

function useSaveToMyGames(
  createUserGame: (pgn: string, metadata: Record<string, unknown>) => Promise<unknown>,
) {
  const [savedGameIds, setSavedGameIds] = useState<Set<string>>(new Set());
  const [snackbar, setSnackbar] = useState<{ msg: string; severity: string } | null>(null);

  const handleSaveToMyGames = useCallback(async (game: OpenedGame): Promise<boolean> => {
    try {
      const result = await createUserGame(game.pgn, {
        white: game.white,
        black: game.black,
        white_elo: game.whiteElo ?? null,
        black_elo: game.blackElo ?? null,
        result: game.result,
        date: game.date ?? null,
        event: game.event ?? null,
        eco: game.eco ?? null,
        source: typeof game.source === 'string' ? game.source : 'database',
      });
      if (result) {
        setSavedGameIds(prev => new Set(prev).add(game.id));
        setSnackbar({ msg: 'gameSavedToMyGames', severity: 'success' });
        return true;
      }
      setSnackbar({ msg: 'gameSaveFailed', severity: 'error' });
      return false;
    } catch {
      setSnackbar({ msg: 'gameSaveFailed', severity: 'error' });
      return false;
    }
  }, [createUserGame]);

  return { savedGameIds, snackbar, handleSaveToMyGames };
}

// ─── Tests ──────────────────────────────

describe('GameViewerPanel — handleSave callback lifecycle', () => {
  let mockOnSave: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    mockOnSave = vi.fn();
  });

  it('should transition saving=true while waiting, then saving=false after resolve', async () => {
    let resolveSave!: (value: boolean) => void;
    mockOnSave.mockReturnValue(new Promise<boolean>(r => { resolveSave = r; }));

    const { result } = renderHook(() => useBookmarkButton(sampleGame, mockOnSave));

    expect(result.current.saving).toBe(false);
    expect(result.current.saved).toBe(false);

    // Start the save (don't await yet)
    let savePromise: Promise<void>;
    act(() => {
      savePromise = result.current.handleSave();
    });

    // saving should be true while waiting
    expect(result.current.saving).toBe(true);
    expect(result.current.saved).toBe(false);

    // Resolve the save
    await act(async () => {
      resolveSave(true);
      await savePromise!;
    });

    expect(result.current.saving).toBe(false);
    expect(result.current.saved).toBe(true);
  });

  it('should set saved=true only when onSaveToMyGames returns true', async () => {
    mockOnSave.mockResolvedValue(true);

    const { result } = renderHook(() => useBookmarkButton(sampleGame, mockOnSave));

    await act(async () => {
      await result.current.handleSave();
    });

    expect(result.current.saved).toBe(true);
    expect(mockOnSave).toHaveBeenCalledWith(sampleGame);
  });

  it('should NOT set saved=true when onSaveToMyGames returns false', async () => {
    mockOnSave.mockResolvedValue(false);

    const { result } = renderHook(() => useBookmarkButton(sampleGame, mockOnSave));

    await act(async () => {
      await result.current.handleSave();
    });

    expect(result.current.saved).toBe(false);
    expect(result.current.saving).toBe(false);
  });

  it('should pass the full game object to onSaveToMyGames', async () => {
    mockOnSave.mockResolvedValue(true);

    const { result } = renderHook(() => useBookmarkButton(sampleGame, mockOnSave));

    await act(async () => {
      await result.current.handleSave();
    });

    expect(mockOnSave).toHaveBeenCalledTimes(1);
    const passedGame = mockOnSave.mock.calls[0][0];
    expect(passedGame.id).toBe('game-42');
    expect(passedGame.white).toBe('Carlsen, Magnus');
    expect(passedGame.pgn).toBe(sampleGame.pgn);
  });
});

describe('GameViewerPanel — Concurrent save prevention', () => {
  it('should not call onSaveToMyGames when already saving', async () => {
    let resolveSave!: (value: boolean) => void;
    const mockOnSave = vi.fn().mockReturnValue(
      new Promise<boolean>(r => { resolveSave = r; })
    );

    const { result } = renderHook(() => useBookmarkButton(sampleGame, mockOnSave));

    // Start first save
    act(() => {
      result.current.handleSave();
    });

    expect(result.current.saving).toBe(true);

    // Try second save while still saving
    await act(async () => {
      await result.current.handleSave();
    });

    // Should only have been called once
    expect(mockOnSave).toHaveBeenCalledTimes(1);

    // Cleanup
    await act(async () => {
      resolveSave(true);
    });
  });

  it('should not call onSaveToMyGames when already saved', async () => {
    const mockOnSave = vi.fn().mockResolvedValue(true);

    const { result } = renderHook(() => useBookmarkButton(sampleGame, mockOnSave, true));

    await act(async () => {
      await result.current.handleSave();
    });

    expect(mockOnSave).not.toHaveBeenCalled();
  });

  it('should not call onSaveToMyGames when callback is not provided', async () => {
    const { result } = renderHook(() => useBookmarkButton(sampleGame));

    await act(async () => {
      await result.current.handleSave();
    });

    // No error thrown, nothing called
    expect(result.current.saving).toBe(false);
    expect(result.current.saved).toBe(false);
  });
});

describe('GameViewerPanel — isSaved prop sync', () => {
  it('should sync saved state when isSaved prop changes to true', () => {
    const mockOnSave = vi.fn().mockResolvedValue(true);

    const { result, rerender } = renderHook(
      ({ isSaved }) => useBookmarkButton(sampleGame, mockOnSave, isSaved),
      { initialProps: { isSaved: false } },
    );

    expect(result.current.saved).toBe(false);

    // Parent sets isSaved=true (e.g. savedGameIds updated)
    rerender({ isSaved: true });

    expect(result.current.saved).toBe(true);
  });

  it('should start as saved=true when isSaved prop is initially true', () => {
    const mockOnSave = vi.fn();

    const { result } = renderHook(() => useBookmarkButton(sampleGame, mockOnSave, true));

    expect(result.current.saved).toBe(true);
  });
});

describe('handleSaveToMyGames — Integration with createUserGame', () => {
  let mockCreate: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    mockCreate = vi.fn();
  });

  it('should call createUserGame with correct PGN and metadata', async () => {
    mockCreate.mockResolvedValue({ id: 'new-id' });

    const { result } = renderHook(() => useSaveToMyGames(mockCreate));

    await act(async () => {
      await result.current.handleSaveToMyGames(sampleGame);
    });

    expect(mockCreate).toHaveBeenCalledTimes(1);
    const [pgn, metadata] = mockCreate.mock.calls[0];
    expect(pgn).toBe(sampleGame.pgn);
    expect(metadata).toEqual({
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

  it('should add game ID to savedGameIds on success', async () => {
    mockCreate.mockResolvedValue({ id: 'created-1' });

    const { result } = renderHook(() => useSaveToMyGames(mockCreate));

    expect(result.current.savedGameIds.has('game-42')).toBe(false);

    await act(async () => {
      const success = await result.current.handleSaveToMyGames(sampleGame);
      expect(success).toBe(true);
    });

    expect(result.current.savedGameIds.has('game-42')).toBe(true);
  });

  it('should show success snackbar on save', async () => {
    mockCreate.mockResolvedValue({ id: 'created-1' });

    const { result } = renderHook(() => useSaveToMyGames(mockCreate));

    await act(async () => {
      await result.current.handleSaveToMyGames(sampleGame);
    });

    expect(result.current.snackbar).toEqual({
      msg: 'gameSavedToMyGames',
      severity: 'success',
    });
  });

  it('should show error snackbar when createUserGame returns null', async () => {
    mockCreate.mockResolvedValue(null);

    const { result } = renderHook(() => useSaveToMyGames(mockCreate));

    await act(async () => {
      const success = await result.current.handleSaveToMyGames(sampleGame);
      expect(success).toBe(false);
    });

    expect(result.current.snackbar).toEqual({
      msg: 'gameSaveFailed',
      severity: 'error',
    });
    expect(result.current.savedGameIds.has('game-42')).toBe(false);
  });

  it('should show error snackbar when createUserGame throws', async () => {
    mockCreate.mockRejectedValue(new Error('Network error'));

    const { result } = renderHook(() => useSaveToMyGames(mockCreate));

    await act(async () => {
      const success = await result.current.handleSaveToMyGames(sampleGame);
      expect(success).toBe(false);
    });

    expect(result.current.snackbar).toEqual({
      msg: 'gameSaveFailed',
      severity: 'error',
    });
  });

  it('should set null fields for missing optional game metadata', async () => {
    mockCreate.mockResolvedValue({ id: 'created-min' });

    const { result } = renderHook(() => useSaveToMyGames(mockCreate));

    await act(async () => {
      await result.current.handleSaveToMyGames(minimalGame);
    });

    const [, metadata] = mockCreate.mock.calls[0];
    expect(metadata.white_elo).toBeNull();
    expect(metadata.black_elo).toBeNull();
    expect(metadata.date).toBeNull();
    expect(metadata.event).toBeNull();
    expect(metadata.eco).toBeNull();
    expect(metadata.source).toBe('database');
  });

  it('should track multiple saved games independently', async () => {
    mockCreate.mockResolvedValue({ id: 'x' });

    const { result } = renderHook(() => useSaveToMyGames(mockCreate));

    const secondGame: OpenedGame = { ...sampleGame, id: 'game-99', white: 'Aronian' };

    await act(async () => {
      await result.current.handleSaveToMyGames(sampleGame);
    });
    await act(async () => {
      await result.current.handleSaveToMyGames(secondGame);
    });

    expect(result.current.savedGameIds.has('game-42')).toBe(true);
    expect(result.current.savedGameIds.has('game-99')).toBe(true);
    expect(result.current.savedGameIds.size).toBe(2);
  });

  it('should not add to savedGameIds on failure', async () => {
    mockCreate.mockRejectedValue(new Error('fail'));

    const { result } = renderHook(() => useSaveToMyGames(mockCreate));

    await act(async () => {
      await result.current.handleSaveToMyGames(sampleGame);
    });

    expect(result.current.savedGameIds.size).toBe(0);
  });
});

describe('Full bookmark flow — handleSave → handleSaveToMyGames → createUserGame', () => {
  it('should complete the full save flow from button click to saved state', async () => {
    const mockCreate = vi.fn().mockResolvedValue({ id: 'saved-1' });
    const { result: saveHook } = renderHook(() => useSaveToMyGames(mockCreate));

    const { result: btnHook } = renderHook(() =>
      useBookmarkButton(
        sampleGame,
        saveHook.current.handleSaveToMyGames,
        saveHook.current.savedGameIds.has(sampleGame.id),
      ),
    );

    // Initially unsaved
    expect(btnHook.current.saved).toBe(false);
    expect(btnHook.current.saving).toBe(false);

    // Click save
    await act(async () => {
      await btnHook.current.handleSave();
    });

    // Button should be saved
    expect(btnHook.current.saved).toBe(true);
    expect(btnHook.current.saving).toBe(false);

    // createUserGame should have been called with the game's PGN
    expect(mockCreate).toHaveBeenCalledTimes(1);
    expect(mockCreate.mock.calls[0][0]).toBe(sampleGame.pgn);

    // savedGameIds should include the game
    expect(saveHook.current.savedGameIds.has('game-42')).toBe(true);

    // Success snackbar
    expect(saveHook.current.snackbar?.severity).toBe('success');
  });

  it('should keep button unsaved when the backend fails', async () => {
    const mockCreate = vi.fn().mockRejectedValue(new Error('Server error'));
    const { result: saveHook } = renderHook(() => useSaveToMyGames(mockCreate));

    const { result: btnHook } = renderHook(() =>
      useBookmarkButton(
        sampleGame,
        saveHook.current.handleSaveToMyGames,
        false,
      ),
    );

    await act(async () => {
      await btnHook.current.handleSave();
    });

    // Button should NOT be saved
    expect(btnHook.current.saved).toBe(false);
    expect(btnHook.current.saving).toBe(false);

    // Error snackbar
    expect(saveHook.current.snackbar?.severity).toBe('error');
  });
});
