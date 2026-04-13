import { describe, it, expect } from 'vitest';

/**
 * Database Page — My Games Tab Integration Tests
 *
 * Tests the tab switching logic and game-close behavior
 * that was added to integrate the My Games panel into the Database page.
 */

describe('My Games Tab Navigation', () => {
  // Replicate the tab state logic from DebutPage
  const HOME_TABS = ['debut', 'my-games'];

  function isHomeTab(tab: string): boolean {
    return HOME_TABS.includes(tab);
  }

  function isGameTab(tab: string): boolean {
    return !isHomeTab(tab);
  }

  it('should recognize "debut" as a home tab', () => {
    expect(isHomeTab('debut')).toBe(true);
  });

  it('should recognize "my-games" as a home tab', () => {
    expect(isHomeTab('my-games')).toBe(true);
  });

  it('should recognize game IDs as game tabs', () => {
    expect(isGameTab('game-123')).toBe(true);
    expect(isGameTab('Carlsen-Nepomniachtchi-2021')).toBe(true);
  });

  it('should not recognize home tabs as game tabs', () => {
    expect(isGameTab('debut')).toBe(false);
    expect(isGameTab('my-games')).toBe(false);
  });
});

describe('Close Game Tab — Return to Last Home Tab', () => {
  // Simulates the lastHomeTabRef logic
  function simulateCloseGame(
    activeTab: string,
    closingGameId: string,
    lastHomeTab: string
  ): string {
    if (activeTab === closingGameId) {
      return lastHomeTab;
    }
    return activeTab;
  }

  it('should return to "debut" when last home tab was debut', () => {
    const result = simulateCloseGame('game-123', 'game-123', 'debut');
    expect(result).toBe('debut');
  });

  it('should return to "my-games" when last home tab was my-games', () => {
    const result = simulateCloseGame('game-456', 'game-456', 'my-games');
    expect(result).toBe('my-games');
  });

  it('should not change tab when closing a non-active game', () => {
    const result = simulateCloseGame('game-123', 'game-456', 'my-games');
    expect(result).toBe('game-123');
  });

  it('should not change tab when on debut and closing a game', () => {
    const result = simulateCloseGame('debut', 'game-123', 'debut');
    expect(result).toBe('debut');
  });
});

describe('Last Home Tab Tracking', () => {
  function updateLastHomeTab(activeTab: string, currentLastHome: string): string {
    if (activeTab === 'debut' || activeTab === 'my-games') {
      return activeTab;
    }
    return currentLastHome;
  }

  it('should update when switching to debut', () => {
    expect(updateLastHomeTab('debut', 'my-games')).toBe('debut');
  });

  it('should update when switching to my-games', () => {
    expect(updateLastHomeTab('my-games', 'debut')).toBe('my-games');
  });

  it('should not update when switching to a game tab', () => {
    expect(updateLastHomeTab('game-123', 'my-games')).toBe('my-games');
  });

  it('should preserve debut when opening multiple games', () => {
    let lastHome = 'debut';
    lastHome = updateLastHomeTab('game-1', lastHome);
    lastHome = updateLastHomeTab('game-2', lastHome);
    lastHome = updateLastHomeTab('game-3', lastHome);
    expect(lastHome).toBe('debut');
  });

  it('should preserve my-games when opening multiple games', () => {
    let lastHome = 'my-games';
    lastHome = updateLastHomeTab('game-1', lastHome);
    lastHome = updateLastHomeTab('game-2', lastHome);
    expect(lastHome).toBe('my-games');
  });
});

describe('Active Tab Content Routing', () => {
  type ContentPanel = 'repertoire' | 'my-games' | 'game-viewer' | 'none';

  function getContentPanel(activeTab: string, hasActiveGame: boolean): ContentPanel {
    if (activeTab === 'debut') return 'repertoire';
    if (activeTab === 'my-games') return 'my-games';
    if (hasActiveGame) return 'game-viewer';
    return 'none';
  }

  it('should show repertoire panel for debut tab', () => {
    expect(getContentPanel('debut', false)).toBe('repertoire');
  });

  it('should show my-games panel for my-games tab', () => {
    expect(getContentPanel('my-games', false)).toBe('my-games');
  });

  it('should show game viewer when a game is active', () => {
    expect(getContentPanel('game-123', true)).toBe('game-viewer');
  });

  it('should show none when game tab has no matching game', () => {
    expect(getContentPanel('game-999', false)).toBe('none');
  });
});

describe('Board Behavior Per Tab', () => {
  function isBoardInteractive(activeTab: string, hasActiveGame: boolean = false, isEditable: boolean = false): boolean {
    if (activeTab === 'debut') return true;
    if (activeTab === 'my-games' && !hasActiveGame) return true;
    if (isEditable) return true;
    return false;
  }

  function showStockfish(activeTab: string): boolean {
    return activeTab === 'debut';
  }

  function showMoveNotation(activeTab: string): boolean {
    return activeTab === 'debut';
  }

  function showGameViewer(activeTab: string, hasActiveGame: boolean): boolean {
    return activeTab !== 'debut' && hasActiveGame;
  }

  it('should have interactive board in debut tab', () => {
    expect(isBoardInteractive('debut')).toBe(true);
  });

  it('should have interactive board in my-games tab when no game is open', () => {
    expect(isBoardInteractive('my-games', false)).toBe(true);
  });

  it('should not have interactive board on non-editable game tab', () => {
    expect(isBoardInteractive('game-123', true, false)).toBe(false);
  });

  it('should have interactive board on editable game tab', () => {
    expect(isBoardInteractive('game-123', true, true)).toBe(true);
  });

  it('should show stockfish only in debut tab', () => {
    expect(showStockfish('debut')).toBe(true);
    expect(showStockfish('my-games')).toBe(false);
  });

  it('should show move notation only in debut tab', () => {
    expect(showMoveNotation('debut')).toBe(true);
    expect(showMoveNotation('my-games')).toBe(false);
  });

  it('should show game viewer for opened game tabs', () => {
    expect(showGameViewer('game-123', true)).toBe(true);
    expect(showGameViewer('my-games', false)).toBe(false);
    expect(showGameViewer('debut', false)).toBe(false);
  });
});

describe('My Games Board Interaction — Move History', () => {
  const STARTING_FEN = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1';
  const FEN_AFTER_E4 = 'rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1';
  const FEN_AFTER_E4_E5 = 'rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR w KQkq e6 0 2';
  const FEN_AFTER_E4_E5_NF3 = 'rnbqkbnr/pppp1ppp/8/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R b KQkq - 1 2';

  // Simulate the state management logic from page.tsx
  function createMoveState() {
    let moveHistory: string[] = [STARTING_FEN];
    let moveIndex = 0;

    return {
      get fen() { return moveHistory[moveIndex]; },
      get history() { return moveHistory; },
      get index() { return moveIndex; },
      addMove(newFen: string) {
        moveHistory = [...moveHistory.slice(0, moveIndex + 1), newFen];
        moveIndex += 1;
      },
      reset() {
        moveHistory = [STARTING_FEN];
        moveIndex = 0;
      },
      prev() {
        moveIndex = Math.max(0, moveIndex - 1);
      },
      next() {
        moveIndex = Math.min(moveHistory.length - 1, moveIndex + 1);
      },
      goToEnd() {
        moveIndex = moveHistory.length - 1;
      },
    };
  }

  it('should start with the initial FEN position', () => {
    const state = createMoveState();
    expect(state.fen).toBe(STARTING_FEN);
    expect(state.index).toBe(0);
    expect(state.history).toHaveLength(1);
  });

  it('should add a move and update FEN', () => {
    const state = createMoveState();
    state.addMove(FEN_AFTER_E4);
    expect(state.fen).toBe(FEN_AFTER_E4);
    expect(state.index).toBe(1);
    expect(state.history).toHaveLength(2);
  });

  it('should allow multiple moves (white and black alternate)', () => {
    const state = createMoveState();
    state.addMove(FEN_AFTER_E4);
    state.addMove(FEN_AFTER_E4_E5);
    state.addMove(FEN_AFTER_E4_E5_NF3);

    expect(state.fen).toBe(FEN_AFTER_E4_E5_NF3);
    expect(state.index).toBe(3);
    expect(state.history).toHaveLength(4);
  });

  it('should navigate backwards with prev()', () => {
    const state = createMoveState();
    state.addMove(FEN_AFTER_E4);
    state.addMove(FEN_AFTER_E4_E5);

    state.prev();
    expect(state.fen).toBe(FEN_AFTER_E4);
    expect(state.index).toBe(1);

    state.prev();
    expect(state.fen).toBe(STARTING_FEN);
    expect(state.index).toBe(0);
  });

  it('should not go before the starting position', () => {
    const state = createMoveState();
    state.prev();
    expect(state.fen).toBe(STARTING_FEN);
    expect(state.index).toBe(0);
  });

  it('should navigate forward with next()', () => {
    const state = createMoveState();
    state.addMove(FEN_AFTER_E4);
    state.addMove(FEN_AFTER_E4_E5);

    state.prev();
    state.prev();
    expect(state.fen).toBe(STARTING_FEN);

    state.next();
    expect(state.fen).toBe(FEN_AFTER_E4);
    state.next();
    expect(state.fen).toBe(FEN_AFTER_E4_E5);
  });

  it('should not go beyond the last move with next()', () => {
    const state = createMoveState();
    state.addMove(FEN_AFTER_E4);
    state.next();
    expect(state.fen).toBe(FEN_AFTER_E4);
    expect(state.index).toBe(1);
  });

  it('should reset to starting position', () => {
    const state = createMoveState();
    state.addMove(FEN_AFTER_E4);
    state.addMove(FEN_AFTER_E4_E5);

    state.reset();
    expect(state.fen).toBe(STARTING_FEN);
    expect(state.index).toBe(0);
    expect(state.history).toHaveLength(1);
  });

  it('should go to end position', () => {
    const state = createMoveState();
    state.addMove(FEN_AFTER_E4);
    state.addMove(FEN_AFTER_E4_E5);
    state.addMove(FEN_AFTER_E4_E5_NF3);

    state.prev();
    state.prev();
    expect(state.fen).toBe(FEN_AFTER_E4);

    state.goToEnd();
    expect(state.fen).toBe(FEN_AFTER_E4_E5_NF3);
    expect(state.index).toBe(3);
  });

  it('should truncate future moves when adding a move from a past position', () => {
    const state = createMoveState();
    state.addMove(FEN_AFTER_E4);
    state.addMove(FEN_AFTER_E4_E5);
    state.addMove(FEN_AFTER_E4_E5_NF3);

    // Go back to after e4
    state.prev();
    state.prev();
    expect(state.fen).toBe(FEN_AFTER_E4);

    // Play a different move — should truncate the old continuation
    const differentFen = 'rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 2';
    state.addMove(differentFen);
    expect(state.fen).toBe(differentFen);
    expect(state.history).toHaveLength(3); // starting + e4 + new move
    expect(state.index).toBe(2);
  });
});

describe('My Games Board — FEN and Handler Routing', () => {
  const STARTING_FEN = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1';
  const MY_GAMES_FEN = 'rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1';

  // Simulate the FEN selection logic from page.tsx DebutBoard props
  function getBoardFen(
    activeTab: string,
    activeGame: { startingFen: string } | null,
    myGamesFen: string,
    editTreeFen: string | null,
    activeGameFen: string | null,
    boardFen: string
  ): string {
    if (activeTab === 'my-games' && !activeGame) return myGamesFen;
    return editTreeFen || activeGameFen || boardFen;
  }

  it('should use myGamesFen when on my-games tab with no game open', () => {
    const fen = getBoardFen('my-games', null, MY_GAMES_FEN, null, null, STARTING_FEN);
    expect(fen).toBe(MY_GAMES_FEN);
  });

  it('should use boardFen when on debut tab', () => {
    const fen = getBoardFen('debut', null, MY_GAMES_FEN, null, null, STARTING_FEN);
    expect(fen).toBe(STARTING_FEN);
  });

  it('should use editTreeFen when available (editable game)', () => {
    const editFen = 'some-edit-fen';
    const fen = getBoardFen('game-123', { startingFen: STARTING_FEN }, MY_GAMES_FEN, editFen, null, STARTING_FEN);
    expect(fen).toBe(editFen);
  });

  // Simulate the onMove handler routing logic from page.tsx
  type MoveHandler = 'repertoire' | 'game-edit' | 'my-games-browse' | 'noop';

  function getMoveHandler(
    activeTab: string,
    isActiveGameEditable: boolean,
    activeGame: boolean
  ): MoveHandler {
    if (activeTab === 'debut') return 'repertoire';
    if (isActiveGameEditable) return 'game-edit';
    if (activeTab === 'my-games' && !activeGame) return 'my-games-browse';
    return 'noop';
  }

  it('should use repertoire handler for debut tab', () => {
    expect(getMoveHandler('debut', false, false)).toBe('repertoire');
  });

  it('should use game-edit handler for editable games', () => {
    expect(getMoveHandler('game-123', true, true)).toBe('game-edit');
  });

  it('should use my-games-browse handler for my-games tab with no game', () => {
    expect(getMoveHandler('my-games', false, false)).toBe('my-games-browse');
  });

  it('should use noop for non-editable game tabs', () => {
    expect(getMoveHandler('game-123', false, true)).toBe('noop');
  });
});
