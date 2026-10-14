import { describe, it, expect } from 'vitest';
import { readFileSync } from 'fs';
import { resolve } from 'path';
import { parseGamePgn } from '@/components/openings/GameViewerPanel';

const coachPageContent = readFileSync(resolve(__dirname, '../page.tsx'), 'utf-8');
const coachChatContent = readFileSync(
  resolve(__dirname, '../../../components/coach/CoachChat.tsx'),
  'utf-8'
);
// The conversation (and its game cards) renders in MessageList since the P1 split.
const messageListContent = readFileSync(
  resolve(__dirname, '../../../components/coach/MessageList.tsx'),
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
    expect(coachChatContent).toContain('onOpenGame={onOpenGame}');
    expect(messageListContent).toContain('onClick={() => onOpenGame?.(game)}');
  });

  it('does not use window.open for game results', () => {
    expect(coachChatContent).not.toContain('window.open');
    expect(messageListContent).not.toContain('window.open');
  });
});

describe('CoachPage - Game Tabs', () => {
  it('shows game tabs with the coach\'s own viewer pieces, not the MUI GameViewerPanel', () => {
    expect(coachPageContent).not.toContain('<GameViewerPanel');
    expect(coachPageContent).toContain("import ViewerTabsSheet from '@/components/coach/ViewerTabsSheet'");
    expect(coachPageContent).toContain("import ViewerMoveList from '@/components/coach/ViewerMoveList'");
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

  it('takes the active game tab from the mode reducer', () => {
    expect(coachPageContent).toContain('useReducer(coachMode, initialCoachMode)');
    expect(coachPageContent).toContain('const activeGameId = modeState.viewerId');
  });

  it('has gameMoveIndices state', () => {
    expect(coachPageContent).toContain('useState<Record<string, number>>({})');
  });

  it('passes onOpenGame to CoachChat', () => {
    expect(coachPageContent).toContain('onOpenGame={handleOpenGame}');
  });

  it('renders the tabs stack chip when games are open', () => {
    expect(coachPageContent).toContain('openedGames.length > 0 && (');
    expect(coachPageContent).toContain('<ViewerTabsSheet');
    expect(coachPageContent).toContain('title: `${g.white} vs ${g.black}`');
  });

  it('renders the tap-to-jump move list when a game tab is active', () => {
    expect(coachPageContent).toContain('<ViewerMoveList');
    expect(coachPageContent).toContain('onJump={(index) => jumpTab(activeGameId, () => index)}');
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
    // Tabs are keyed by server board id now, so an already-open game is
    // recognised by its TWIC metadata rather than the TWIC id.
    expect(coachPageContent).toContain("openedGames.find((g) => g.source === 'twic' && g.white === game.white_name");
    expect(coachPageContent).toContain('setActiveGameId(existing.id)');
  });

  it('persists tabs as session boards and restores them', () => {
    expect(coachPageContent).toContain("kind: 'master_game'");
    expect(coachPageContent).toContain('coachApi.createBoard(sessionId');
    expect(coachPageContent).toContain('coachApi.deleteBoard(sessionId, gameId)');
    expect(coachPageContent).toContain('coachApi.listBoards(sessionId)');
    expect(coachPageContent).toContain('openedGameFromBoard(b, labels)');
  });

  it('tells the coach which board is active', () => {
    expect(coachPageContent).toContain('boardId={activeBoardId');
    expect(coachPageContent).toContain("coachApi.updateSession(sessionId, { active_board_id: boardId })");
    expect(coachPageContent).toContain('onActiveBoardChanged={handleActiveBoardChanged}');
    expect(coachPageContent).toContain('restoreHistory');
  });

  it('routes actions addressed to a game tab to that tab (navigate, arrows, highlights)', () => {
    expect(coachPageContent).toContain('routeBoardActions(actions, openedGames.map((g) => g.id))');
    expect(coachPageContent).toContain('applyTabActions(');
  });

  it('draws the coach\'s arrows and highlights on viewer boards (no forced empty lists)', () => {
    const activeGameBranch = coachPageContent.split('activeGameId && activeGame ?')[1];
    const trueBranch = activeGameBranch.substring(0, activeGameBranch.indexOf(') : game ? ('));
    expect(trueBranch).not.toContain('arrows={[]}');
    expect(trueBranch).not.toContain('highlights={[]}');
    expect(trueBranch).toContain('viewerAnnotations.arrows');
  });

  it('offers the sessions panel', () => {
    expect(coachPageContent).toContain('<CoachSessions');
    expect(coachPageContent).toContain('onSelect={handleSelectSession}');
  });

  it('closes game tabs from the tabs sheet', () => {
    expect(coachPageContent).toContain('onClose={handleCloseGame}');
  });

  it('conditionally renders game viewer or coach board', () => {
    expect(coachPageContent).toContain('activeGameId && activeGame ?');
  });

  it('renders CoachBoard alongside the move list when game tab is active', () => {
    const activeGameBranch = coachPageContent.split('activeGameId && activeGame ?')[1];
    const trueBranch = activeGameBranch.substring(0, activeGameBranch.indexOf(') : game ? ('));
    expect(trueBranch).toContain('<CoachBoard');
    expect(trueBranch).toContain('<ViewerMoveList');
  });

  it('wires CoachBoard FEN to activeGame when game tab is active', () => {
    // Should use activeGame.startingFen for initial position
    expect(coachPageContent).toContain('activeGame.startingFen');
    // Should use activeGame.fens for navigated positions
    expect(coachPageContent).toContain('activeGame.fens[gameMoveIndices[activeGameId]]');
  });

  it('wires CoachBoard navigation to gameMoveIndices for active game', () => {
    expect(coachPageContent).toContain('onFirst={() => jumpTab(activeGameId, () => -1)}');
    expect(coachPageContent).toContain('onPrev={() => jumpTab(activeGameId, (i) => Math.max(-1, i - 1))}');
    expect(coachPageContent).toContain(
      'onNext={() => jumpTab(activeGameId, (i) => Math.min(activeGame.moves.length - 1, i + 1))}'
    );
    expect(coachPageContent).toContain('onLast={() => jumpTab(activeGameId, () => activeGame.moves.length - 1)}');
    // The student's own navigation clears the coach's arrows for the old position.
    expect(coachPageContent).toContain('[id]: EMPTY_ANNOTATIONS');
  });

  it('sets onMove to a no-op when viewing a game', () => {
    // When activeGame is set, onMove should be a no-op
    expect(coachPageContent).toContain('onMove={() => {}}');
  });

  it('never runs a puzzle on a viewed game', () => {
    const activeGameBranch = coachPageContent.split('activeGameId && activeGame ?')[1];
    const trueBranch = activeGameBranch.substring(0, activeGameBranch.indexOf(') : game ? ('));
    expect(trueBranch).not.toContain('puzzle');
  });

  it('puts the move list beside the board or under it, sized to the board area', () => {
    // Beside the board when it keeps >= 440 px that way, else under it; the size
    // follows the measured board area, not the window (overflow on laptops, 2026-09-29).
    expect(coachPageContent).toContain("layout={gameLayout.beside ? 'list' : 'strip'}");
    expect(coachPageContent).toContain('gameLayout.beside');
    expect(coachPageContent).toContain('ref={measureBoardArea}');
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
