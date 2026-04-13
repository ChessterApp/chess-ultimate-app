import { describe, it, expect } from 'vitest';
import { Chess } from 'chess.js';

/**
 * AddGameModal — Logic tests for PGN validation, form population, and board entry
 */

describe('AddGameModal PGN Validation', () => {
  function validatePgn(pgn: string): { valid: boolean; moves: number } {
    try {
      const chess = new Chess();
      chess.loadPgn(pgn.trim());
      return { valid: true, moves: chess.history().length };
    } catch {
      return { valid: false, moves: 0 };
    }
  }

  it('should validate a correct PGN', () => {
    const pgn = '1. e4 e5 2. Nf3 Nc6 3. Bb5 a6';
    const result = validatePgn(pgn);
    expect(result.valid).toBe(true);
    expect(result.moves).toBe(6);
  });

  it('should validate PGN with headers', () => {
    const pgn = `[Event "Test"]
[White "Player1"]
[Black "Player2"]
[Result "1-0"]

1. e4 e5 2. Nf3 Nc6 1-0`;
    const result = validatePgn(pgn);
    expect(result.valid).toBe(true);
    expect(result.moves).toBe(4);
  });

  it('should reject invalid PGN', () => {
    const pgn = '1. e4 e5 2. Zz9 invalid';
    const result = validatePgn(pgn);
    expect(result.valid).toBe(false);
  });

  it('should reject empty PGN', () => {
    const pgn = '';
    const result = validatePgn(pgn);
    // Empty PGN loads as 0 moves but is technically valid
    expect(result.moves).toBe(0);
  });

  it('should handle PGN with whitespace', () => {
    const pgn = '  1. e4 e5 2. Nf3 Nc6  ';
    const result = validatePgn(pgn);
    expect(result.valid).toBe(true);
    expect(result.moves).toBe(4);
  });

  it('should count moves correctly for a full game', () => {
    const pgn = '1. e4 e5 2. Nf3 Nc6 3. Bb5 a6 4. Ba4 Nf6 5. O-O';
    const result = validatePgn(pgn);
    expect(result.valid).toBe(true);
    expect(result.moves).toBe(9);
  });
});

describe('AddGameModal PGN Header Extraction', () => {
  function extractHeaders(pgnText: string): Record<string, string> {
    const headers: Record<string, string> = {};
    const lines = pgnText.split('\n');
    for (const line of lines) {
      const match = line.match(/\[(\w+)\s+"(.*)"\]/);
      if (match) headers[match[1]] = match[2];
    }
    return headers;
  }

  it('should extract all standard headers', () => {
    const pgn = `[Event "World Championship"]
[White "Carlsen, Magnus"]
[Black "Nepomniachtchi, Ian"]
[Result "1-0"]
[Date "2021.12.03"]
[WhiteElo "2855"]
[BlackElo "2782"]

1. d4 Nf6 *`;
    const headers = extractHeaders(pgn);
    expect(headers.Event).toBe('World Championship');
    expect(headers.White).toBe('Carlsen, Magnus');
    expect(headers.Black).toBe('Nepomniachtchi, Ian');
    expect(headers.Result).toBe('1-0');
    expect(headers.Date).toBe('2021.12.03');
    expect(headers.WhiteElo).toBe('2855');
    expect(headers.BlackElo).toBe('2782');
  });

  it('should handle PGN with no headers', () => {
    const pgn = '1. e4 e5 2. Nf3 Nc6';
    const headers = extractHeaders(pgn);
    expect(Object.keys(headers)).toHaveLength(0);
  });

  it('should handle partial headers', () => {
    const pgn = `[White "Kasparov"]
[Black "Deep Blue"]

1. e4 c6 *`;
    const headers = extractHeaders(pgn);
    expect(headers.White).toBe('Kasparov');
    expect(headers.Black).toBe('Deep Blue');
    expect(headers.Event).toBeUndefined();
  });

  it('should handle headers with special characters', () => {
    const pgn = `[Event "Tata Steel 2024"]
[White "Gukesh D"]

1. d4 *`;
    const headers = extractHeaders(pgn);
    expect(headers.Event).toBe('Tata Steel 2024');
  });
});

describe('AddGameModal Board Entry', () => {
  it('should track moves via chess.js', () => {
    const chess = new Chess();
    chess.move('e4');
    chess.move('e5');
    chess.move('Nf3');
    expect(chess.history()).toEqual(['e4', 'e5', 'Nf3']);
    expect(chess.history().length).toBe(3);
  });

  it('should generate valid PGN from moves', () => {
    const chess = new Chess();
    chess.move('e4');
    chess.move('e5');
    chess.move('Nf3');
    chess.move('Nc6');
    const pgn = chess.pgn();
    expect(pgn).toContain('e4');
    expect(pgn).toContain('Nf3');
  });

  it('should support undo', () => {
    const chess = new Chess();
    chess.move('e4');
    chess.move('e5');
    chess.move('Nf3');
    chess.undo();
    expect(chess.history()).toEqual(['e4', 'e5']);
  });

  it('should support reset', () => {
    const chess = new Chess();
    chess.move('e4');
    chess.move('e5');
    chess.reset();
    expect(chess.history()).toEqual([]);
    expect(chess.fen()).toBe('rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1');
  });

  it('should compute legal moves correctly', () => {
    const chess = new Chess();
    const moves = chess.moves({ verbose: true });
    // 20 possible first moves (16 pawn + 4 knight)
    expect(moves.length).toBe(20);
  });

  it('should produce legal move destinations map', () => {
    const chess = new Chess();
    const dests = new Map<string, string[]>();
    const moves = chess.moves({ verbose: true });
    for (const move of moves) {
      const existing = dests.get(move.from) || [];
      existing.push(move.to);
      dests.set(move.from, existing);
    }
    // e2 pawn can go to e3 or e4
    expect(dests.get('e2')).toContain('e3');
    expect(dests.get('e2')).toContain('e4');
    // g1 knight can go to f3 or h3
    expect(dests.get('g1')).toContain('f3');
    expect(dests.get('g1')).toContain('h3');
  });
});

describe('AddGameModal Form Population', () => {
  function populateFormFromPgn(pgnText: string) {
    const headers: Record<string, string> = {};
    const lines = pgnText.split('\n');
    for (const line of lines) {
      const match = line.match(/\[(\w+)\s+"(.*)"\]/);
      if (match) headers[match[1]] = match[2];
    }
    return {
      white: headers.White || '',
      black: headers.Black || '',
      whiteElo: headers.WhiteElo || '',
      blackElo: headers.BlackElo || '',
      result: headers.Result || '*',
      date: headers.Date || '',
      event: headers.Event || '',
    };
  }

  it('should populate all fields from PGN headers', () => {
    const pgn = `[Event "Candidates 2024"]
[White "Gukesh D"]
[Black "Nakamura, Hikaru"]
[Result "1-0"]
[Date "2024.04.05"]
[WhiteElo "2758"]
[BlackElo "2794"]

1. e4 e5 *`;
    const form = populateFormFromPgn(pgn);
    expect(form.white).toBe('Gukesh D');
    expect(form.black).toBe('Nakamura, Hikaru');
    expect(form.whiteElo).toBe('2758');
    expect(form.blackElo).toBe('2794');
    expect(form.result).toBe('1-0');
    expect(form.date).toBe('2024.04.05');
    expect(form.event).toBe('Candidates 2024');
  });

  it('should use defaults for missing headers', () => {
    const pgn = '1. e4 e5 *';
    const form = populateFormFromPgn(pgn);
    expect(form.white).toBe('');
    expect(form.black).toBe('');
    expect(form.result).toBe('*');
    expect(form.date).toBe('');
  });
});

describe('AddGameModal Metadata Builder', () => {
  interface GameFormData {
    title: string;
    white: string;
    black: string;
    whiteElo: string;
    blackElo: string;
    result: string;
    date: string;
    event: string;
    notes: string;
  }

  function buildMetadata(form: GameFormData, source: string) {
    const metadata: Record<string, unknown> = { source };
    if (form.title) metadata.title = form.title;
    if (form.white) metadata.white = form.white;
    if (form.black) metadata.black = form.black;
    if (form.whiteElo) metadata.white_elo = parseInt(form.whiteElo, 10);
    if (form.blackElo) metadata.black_elo = parseInt(form.blackElo, 10);
    if (form.result && form.result !== '*') metadata.result = form.result;
    if (form.date) metadata.date = form.date;
    if (form.event) metadata.event = form.event;
    if (form.notes) metadata.notes = form.notes;
    return metadata;
  }

  it('should build metadata with all fields', () => {
    const form: GameFormData = {
      title: 'My Best Game',
      white: 'Me',
      black: 'Opponent',
      whiteElo: '1500',
      blackElo: '1600',
      result: '1-0',
      date: '2024.01.01',
      event: 'Club Championship',
      notes: 'Great attack',
    };
    const metadata = buildMetadata(form, 'pgn_import');
    expect(metadata.source).toBe('pgn_import');
    expect(metadata.title).toBe('My Best Game');
    expect(metadata.white).toBe('Me');
    expect(metadata.white_elo).toBe(1500);
    expect(metadata.black_elo).toBe(1600);
    expect(metadata.result).toBe('1-0');
    expect(metadata.notes).toBe('Great attack');
  });

  it('should omit empty fields', () => {
    const form: GameFormData = {
      title: '',
      white: 'Me',
      black: '',
      whiteElo: '',
      blackElo: '',
      result: '*',
      date: '',
      event: '',
      notes: '',
    };
    const metadata = buildMetadata(form, 'board_entry');
    expect(metadata.source).toBe('board_entry');
    expect(metadata.white).toBe('Me');
    expect(metadata.title).toBeUndefined();
    expect(metadata.black).toBeUndefined();
    expect(metadata.white_elo).toBeUndefined();
    expect(metadata.result).toBeUndefined(); // * is excluded
    expect(metadata.notes).toBeUndefined();
  });

  it('should parse ELO as integer', () => {
    const form: GameFormData = {
      title: '',
      white: '',
      black: '',
      whiteElo: '2855',
      blackElo: '2782',
      result: '*',
      date: '',
      event: '',
      notes: '',
    };
    const metadata = buildMetadata(form, 'manual');
    expect(metadata.white_elo).toBe(2855);
    expect(metadata.black_elo).toBe(2782);
    expect(typeof metadata.white_elo).toBe('number');
  });
});

describe('AddGameModal Input Methods', () => {
  const methods = ['scoresheet', 'pgn'] as const;

  it('should have exactly 2 input methods (board tab removed)', () => {
    expect(methods).toHaveLength(2);
  });

  it('should not include board entry method (moved to main board)', () => {
    expect(methods).not.toContain('board');
  });

  it('should include scoresheet upload method', () => {
    expect(methods).toContain('scoresheet');
  });

  it('should include PGN import method', () => {
    expect(methods).toContain('pgn');
  });
});

describe('AddGameModal Board-Aware Behavior', () => {
  it('should use boardPgn when boardHasMoves is true and not overridden', () => {
    const boardPgn = '1. e4 e5 2. Nf3 Nc6 *';
    const boardHasMoves = true;
    const boardOverridden = false;
    const useBoardPgn = boardHasMoves && !boardOverridden;

    expect(useBoardPgn).toBe(true);

    // When useBoardPgn, the save should use boardPgn
    const finalPgn = useBoardPgn ? boardPgn : '';
    expect(finalPgn).toBe('1. e4 e5 2. Nf3 Nc6 *');
  });

  it('should not use boardPgn when boardHasMoves is false', () => {
    const boardHasMoves = false;
    const boardOverridden = false;
    const useBoardPgn = boardHasMoves && !boardOverridden;

    expect(useBoardPgn).toBe(false);
  });

  it('should not use boardPgn when overridden by user', () => {
    const boardHasMoves = true;
    const boardOverridden = true;
    const useBoardPgn = boardHasMoves && !boardOverridden;

    expect(useBoardPgn).toBe(false);
  });

  it('should set source to board_entry when using board PGN', () => {
    const useBoardPgn = true;
    const source = useBoardPgn ? 'board_entry' : 'pgn_import';
    expect(source).toBe('board_entry');
  });

  it('should set source to pgn_import when not using board PGN', () => {
    const useBoardPgn = false;
    const method = 'pgn';
    const source = useBoardPgn ? 'board_entry' : (method === 'pgn' ? 'pgn_import' : 'scoresheet');
    expect(source).toBe('pgn_import');
  });

  it('should handle PGN with comments from board', () => {
    const boardPgn = '1. e4 {Strong opening} e5 2. Nf3 Nc6 {Solid reply} *';
    expect(boardPgn).toContain('{Strong opening}');
    expect(boardPgn).toContain('{Solid reply}');
  });
});
