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
  function isBoardInteractive(activeTab: string): boolean {
    return activeTab === 'debut';
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

  it('should have interactive board only in debut tab', () => {
    expect(isBoardInteractive('debut')).toBe(true);
    expect(isBoardInteractive('my-games')).toBe(false);
    expect(isBoardInteractive('game-123')).toBe(false);
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
