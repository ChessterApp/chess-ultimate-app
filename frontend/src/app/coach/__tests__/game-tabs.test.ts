import { describe, it, expect } from 'vitest';
import { readFileSync } from 'fs';
import { resolve } from 'path';
import { parseGamePgn } from '@/components/openings/GameViewerPanel';

const coachPageContent = readFileSync(resolve(__dirname, '../page.tsx'), 'utf-8');
const coachChatContent = readFileSync(
  resolve(__dirname, '../../../components/coach/CoachChat.tsx'),
  'utf-8'
);

describe('CoachChat - onOpenGame callback', () => {
  it('accepts onOpenGame prop in interface', () => {
    expect(coachChatContent).toContain('onOpenGame?: (game: GameResult) => void');
  });

  it('destructures onOpenGame from props', () => {
    expect(coachChatContent).toContain('onOpenGame,');
  });

  it('calls onOpenGame instead of window.open on game click', () => {
    expect(coachChatContent).toContain('onClick={() => onOpenGame?.(game)}');
  });

  it('does not use window.open for game results', () => {
    expect(coachChatContent).not.toContain('window.open');
  });
});

describe('CoachPage - Game Tabs', () => {
  it('imports GameViewerPanel', () => {
    expect(coachPageContent).toContain(
      "import GameViewerPanel from '@/components/openings/GameViewerPanel'"
    );
  });

  it('imports OpenedGame type', () => {
    expect(coachPageContent).toContain(
      "import type { OpenedGame } from '@/components/openings/GameViewerPanel'"
    );
  });

  it('imports parseGamePgn', () => {
    expect(coachPageContent).toContain(
      "import { parseGamePgn } from '@/components/openings/GameViewerPanel'"
    );
  });

  it('imports GameResult type', () => {
    expect(coachPageContent).toContain('GameResult');
  });

  it('has openedGames state', () => {
    expect(coachPageContent).toContain('useState<OpenedGame[]>([])');
  });

  it('has activeGameId state', () => {
    expect(coachPageContent).toContain('useState<string | null>(null)');
  });

  it('has gameMoveIndices state', () => {
    expect(coachPageContent).toContain('useState<Record<string, number>>({})');
  });

  it('passes onOpenGame to CoachChat', () => {
    expect(coachPageContent).toContain('onOpenGame={handleOpenGame}');
  });

  it('renders tab bar when games are open', () => {
    expect(coachPageContent).toContain('Coach Board');
    expect(coachPageContent).toContain('{game.white} vs {game.black}');
  });

  it('renders GameViewerPanel when a game tab is active', () => {
    expect(coachPageContent).toContain('<GameViewerPanel');
  });

  it('renders CoachBoard when no game tab is active', () => {
    expect(coachPageContent).toContain('<CoachBoard');
  });

  it('has handleCloseGame that removes games and clears move indices', () => {
    expect(coachPageContent).toContain('handleCloseGame');
    expect(coachPageContent).toContain("prev.filter((g) => g.id !== gameId)");
  });

  it('fetches PGN from the correct API endpoint', () => {
    expect(coachPageContent).toContain('/api/openings/games/${game.id}/pgn');
  });

  it('has a max 10 tabs limit', () => {
    expect(coachPageContent).toContain('openedGames.length >= 10');
  });

  it('switches to existing tab if game already open', () => {
    expect(coachPageContent).toContain('openedGames.some((g) => g.id === gameIdStr)');
  });

  it('has a close button for each game tab', () => {
    expect(coachPageContent).toContain('handleCloseGame(game.id)');
  });

  it('conditionally renders game viewer or coach board', () => {
    expect(coachPageContent).toContain('activeGameId && activeGame ?');
  });

  it('renders CoachBoard alongside GameViewerPanel when game tab is active', () => {
    // The ternary branch for activeGame should contain BOTH components
    const activeGameBranch = coachPageContent.split('activeGameId && activeGame ?')[1];
    const elseIndex = activeGameBranch.indexOf(') : (');
    const trueBranch = activeGameBranch.substring(0, elseIndex);
    expect(trueBranch).toContain('<CoachBoard');
    expect(trueBranch).toContain('<GameViewerPanel');
  });

  it('wires CoachBoard FEN to activeGame when game tab is active', () => {
    // Should use activeGame.startingFen for initial position
    expect(coachPageContent).toContain('activeGame.startingFen');
    // Should use activeGame.fens for navigated positions
    expect(coachPageContent).toContain('activeGame.fens[gameMoveIndices[activeGameId]]');
  });

  it('wires CoachBoard navigation to gameMoveIndices for active game', () => {
    // onFirst sets index to -1 (starting position)
    expect(coachPageContent).toContain("[activeGameId]: -1");
    // onPrev decrements with Math.max(-1, ...)
    expect(coachPageContent).toContain("Math.max(-1, (prev[activeGameId] ?? -1) - 1)");
    // onNext increments with Math.min(moves.length - 1, ...)
    expect(coachPageContent).toContain("Math.min(activeGame.moves.length - 1, (prev[activeGameId] ?? -1) + 1)");
    // onLast sets to last move
    expect(coachPageContent).toContain("[activeGameId]: activeGame.moves.length - 1");
  });

  it('sets onMove to a no-op when viewing a game', () => {
    // When activeGame is set, onMove should be a no-op
    expect(coachPageContent).toContain('onMove={() => {}}');
  });

  it('disables puzzle mode when viewing a game', () => {
    // The game-viewing CoachBoard should have puzzleMode={false}
    const activeGameBranch = coachPageContent.split('activeGameId && activeGame ?')[1];
    const elseIndex = activeGameBranch.indexOf(') : (');
    const trueBranch = activeGameBranch.substring(0, elseIndex);
    expect(trueBranch).toContain('puzzleMode={false}');
    expect(trueBranch).toContain('puzzleState={null}');
  });

  it('wraps GameViewerPanel in a scrollable container with responsive max-height', () => {
    // Mobile: max-h-[150px], Desktop: lg:max-h-[200px]
    expect(coachPageContent).toContain('max-h-[150px]');
    expect(coachPageContent).toContain('lg:max-h-[200px]');
    expect(coachPageContent).toContain('overflow-y-auto');
  });

  it('uses flex-col on mobile and flex-row on desktop for board+panel layout', () => {
    expect(coachPageContent).toContain('flex flex-col lg:flex-row');
  });
});

describe('parseGamePgn integration', () => {
  it('parses a simple PGN into moves and FENs', () => {
    const pgn = '1. e4 e5 2. Nf3 Nc6';
    const result = parseGamePgn(pgn);

    expect(result.moves).toEqual(['e4', 'e5', 'Nf3', 'Nc6']);
    expect(result.fens).toHaveLength(4);
    expect(result.startingFen).toContain('rnbqkbnr/pppppppp');
  });

  it('returns empty arrays for empty PGN', () => {
    const result = parseGamePgn('');
    expect(result.moves).toEqual([]);
    expect(result.fens).toEqual([]);
  });

  it('handles PGN with headers', () => {
    const pgn = '[Event "Test"]\n[White "Carlsen"]\n[Black "Nepomniachtchi"]\n\n1. d4 Nf6 2. c4 e6';
    const result = parseGamePgn(pgn);

    expect(result.moves).toEqual(['d4', 'Nf6', 'c4', 'e6']);
    expect(result.fens).toHaveLength(4);
  });
});
