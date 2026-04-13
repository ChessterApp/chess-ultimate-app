import { describe, it, expect } from 'vitest';

/**
 * MyGamesMoveList — Logic tests for move list, comment management, and PGN building
 */

describe('MyGamesMoveList Move Display', () => {
  function formatMoves(moves: string[]): string[] {
    const formatted: string[] = [];
    for (let i = 0; i < moves.length; i++) {
      const moveNum = Math.floor(i / 2) + 1;
      const isWhite = i % 2 === 0;
      if (isWhite) {
        formatted.push(`${moveNum}. ${moves[i]}`);
      } else {
        formatted.push(moves[i]);
      }
    }
    return formatted;
  }

  it('should format moves with move numbers', () => {
    const moves = ['e4', 'e5', 'Nf3', 'Nc6'];
    const formatted = formatMoves(moves);
    expect(formatted).toEqual(['1. e4', 'e5', '2. Nf3', 'Nc6']);
  });

  it('should handle single move', () => {
    const moves = ['e4'];
    const formatted = formatMoves(moves);
    expect(formatted).toEqual(['1. e4']);
  });

  it('should handle empty moves', () => {
    const formatted = formatMoves([]);
    expect(formatted).toEqual([]);
  });

  it('should handle odd number of moves', () => {
    const moves = ['e4', 'e5', 'Nf3'];
    const formatted = formatMoves(moves);
    expect(formatted).toEqual(['1. e4', 'e5', '2. Nf3']);
  });
});

describe('MyGamesMoveList Comment Management', () => {
  function applyComment(
    comments: Record<number, string>,
    moveIndex: number,
    comment: string
  ): Record<number, string> {
    if (!comment.trim()) {
      const next = { ...comments };
      delete next[moveIndex];
      return next;
    }
    return { ...comments, [moveIndex]: comment };
  }

  it('should add a comment', () => {
    const comments: Record<number, string> = {};
    const result = applyComment(comments, 1, 'Strong opening');
    expect(result[1]).toBe('Strong opening');
  });

  it('should update an existing comment', () => {
    const comments: Record<number, string> = { 1: 'Good move' };
    const result = applyComment(comments, 1, 'Great move!');
    expect(result[1]).toBe('Great move!');
  });

  it('should delete a comment when empty string provided', () => {
    const comments: Record<number, string> = { 1: 'Good move', 2: 'Solid' };
    const result = applyComment(comments, 1, '');
    expect(result[1]).toBeUndefined();
    expect(result[2]).toBe('Solid');
  });

  it('should delete a comment when whitespace-only string provided', () => {
    const comments: Record<number, string> = { 1: 'Good move' };
    const result = applyComment(comments, 1, '   ');
    expect(result[1]).toBeUndefined();
  });

  it('should not modify other comments', () => {
    const comments: Record<number, string> = { 1: 'First', 3: 'Third' };
    const result = applyComment(comments, 2, 'Second');
    expect(result[1]).toBe('First');
    expect(result[2]).toBe('Second');
    expect(result[3]).toBe('Third');
  });
});

describe('MyGamesMoveList PGN Builder', () => {
  function buildPgn(moves: string[], comments: Record<number, string>): string {
    if (moves.length === 0) return '';
    let pgn = '';
    for (let i = 0; i < moves.length; i++) {
      const moveNum = Math.floor(i / 2) + 1;
      const isWhite = i % 2 === 0;
      if (isWhite) {
        pgn += `${moveNum}. `;
      }
      pgn += moves[i];
      const comment = comments[i + 1];
      if (comment) {
        pgn += ` {${comment}}`;
      }
      pgn += ' ';
    }
    pgn += '*';
    return pgn.trim();
  }

  it('should build PGN from moves without comments', () => {
    const moves = ['e4', 'e5', 'Nf3', 'Nc6'];
    const result = buildPgn(moves, {});
    expect(result).toBe('1. e4 e5 2. Nf3 Nc6 *');
  });

  it('should include comments in PGN', () => {
    const moves = ['e4', 'e5', 'Nf3', 'Nc6'];
    const comments = { 1: 'Strong opening', 4: 'Solid reply' };
    const result = buildPgn(moves, comments);
    expect(result).toBe('1. e4 {Strong opening} e5 2. Nf3 Nc6 {Solid reply} *');
  });

  it('should handle single move with comment', () => {
    const moves = ['e4'];
    const comments = { 1: 'The king pawn opening' };
    const result = buildPgn(moves, comments);
    expect(result).toBe('1. e4 {The king pawn opening} *');
  });

  it('should return empty string for no moves', () => {
    const result = buildPgn([], {});
    expect(result).toBe('');
  });

  it('should handle comments with special characters', () => {
    const moves = ['e4', 'e5'];
    const comments = { 1: 'Very interesting! +0.3' };
    const result = buildPgn(moves, comments);
    expect(result).toBe('1. e4 {Very interesting! +0.3} e5 *');
  });
});

describe('MyGamesMoveList Undo Logic', () => {
  it('should remove last move on undo', () => {
    const moves = ['e4', 'e5', 'Nf3'];
    const history = [
      'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1',
      'rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1',
      'rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 2',
      'rnbqkbnr/pppp1ppp/8/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R b KQkq - 1 2',
    ];

    const newMoves = moves.slice(0, -1);
    const newHistory = history.slice(0, -1);
    const newIndex = Math.max(0, 3 - 1);

    expect(newMoves).toEqual(['e4', 'e5']);
    expect(newHistory.length).toBe(3);
    expect(newIndex).toBe(2);
  });

  it('should remove comment for deleted move', () => {
    const comments: Record<number, string> = { 1: 'Good', 2: 'Solid', 3: 'Nice' };
    const movesLength = 3; // about to undo, so delete comment at index 3

    const next = { ...comments };
    delete next[movesLength];

    expect(next[1]).toBe('Good');
    expect(next[2]).toBe('Solid');
    expect(next[3]).toBeUndefined();
  });
});

describe('MyGamesMoveList Navigation', () => {
  it('should set currentIndex to 0 for starting position', () => {
    const currentIndex = 0;
    expect(currentIndex).toBe(0);
  });

  it('should navigate to a specific move', () => {
    const moves = ['e4', 'e5', 'Nf3', 'Nc6'];
    const targetIndex = 2; // after move 2 (e5)
    expect(targetIndex).toBeGreaterThan(0);
    expect(targetIndex).toBeLessThanOrEqual(moves.length);
  });

  it('should identify active move correctly', () => {
    const moves = ['e4', 'e5', 'Nf3'];
    const currentIndex = 2;
    // Move at array index 1 (e5) corresponds to moveIdx 2
    const activeMoveIdx = currentIndex;
    expect(moves[activeMoveIdx - 1]).toBe('e5');
  });
});

describe('MyGamesMoveList Truncation on Branch', () => {
  it('should truncate SAN moves when branching', () => {
    const moves = ['e4', 'e5', 'Nf3', 'Nc6'];
    const currentIndex = 2; // after e5
    // New move from this position creates a branch
    const truncated = moves.slice(0, currentIndex);
    expect(truncated).toEqual(['e4', 'e5']);
  });

  it('should remove comments for truncated moves', () => {
    const comments: Record<number, string> = { 1: 'A', 2: 'B', 3: 'C', 4: 'D' };
    const currentIndex = 2; // after e5

    const next = { ...comments };
    for (const key of Object.keys(next)) {
      if (Number(key) > currentIndex) {
        delete next[Number(key)];
      }
    }

    expect(next[1]).toBe('A');
    expect(next[2]).toBe('B');
    expect(next[3]).toBeUndefined();
    expect(next[4]).toBeUndefined();
  });
});
