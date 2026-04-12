import { describe, it, expect, beforeEach } from 'vitest';
import { pgnToTree, treeToPgn, findNodeById, findParentOf, cloneTree } from '../useGameMoveTree';
import type { OpeningNode } from '../useOpeningRepertoire';

const STARTING_FEN = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1';

// Helper: collect main line moves from tree
function mainLineMoves(root: OpeningNode): string[] {
  const moves: string[] = [];
  let node = root;
  while (node.children && node.children.length > 0) {
    node = node.children[0];
    if (node.move_san) moves.push(node.move_san);
  }
  return moves;
}

// Helper: get all moves at depth 1 from a node (its children's SANs)
function childMoves(node: OpeningNode): string[] {
  return (node.children || []).map(c => c.move_san!).filter(Boolean);
}

describe('pgnToTree', () => {
  it('parses a simple game', () => {
    const tree = pgnToTree('1. e4 e5 2. Nf3 Nc6');
    expect(tree.fen).toBe(STARTING_FEN);
    expect(mainLineMoves(tree)).toEqual(['e4', 'e5', 'Nf3', 'Nc6']);
  });

  it('parses empty PGN', () => {
    const tree = pgnToTree('');
    expect(tree.fen).toBe(STARTING_FEN);
    expect(tree.children).toEqual([]);
  });

  it('parses PGN with result', () => {
    const tree = pgnToTree('1. e4 e5 1-0');
    expect(mainLineMoves(tree)).toEqual(['e4', 'e5']);
  });

  it('parses PGN with headers', () => {
    const pgn = '[Event "Test"]\n[White "Player1"]\n[Black "Player2"]\n\n1. d4 d5 2. c4 e6';
    const tree = pgnToTree(pgn);
    expect(mainLineMoves(tree)).toEqual(['d4', 'd5', 'c4', 'e6']);
  });

  it('parses PGN with a variation', () => {
    const pgn = '1. e4 e5 2. Nf3 (2. Bc4) 2... Nc6';
    const tree = pgnToTree(pgn);
    // Main line: e4 e5 Nf3 Nc6
    expect(mainLineMoves(tree)).toEqual(['e4', 'e5', 'Nf3', 'Nc6']);

    // After e5, there should be 2 children: Nf3 (main) and Bc4 (variation)
    const e5Node = tree.children![0].children![0]; // e4 -> e5
    expect(childMoves(e5Node)).toEqual(['Nf3', 'Bc4']);
  });

  it('parses PGN with nested variations', () => {
    const pgn = '1. e4 e5 (1... c5 (1... e6)) 2. Nf3';
    const tree = pgnToTree(pgn);
    // Main: e4 e5 Nf3
    expect(mainLineMoves(tree)).toEqual(['e4', 'e5', 'Nf3']);

    // e4 has children: e5 (main), c5 (variation), e6 (nested variation)
    // In PGN, (1... e6) nested inside (1... c5) is a sub-variation
    // of the position before c5, which is the position after e4.
    // So all three are children of e4.
    const e4Node = tree.children![0];
    expect(childMoves(e4Node)).toContain('e5');
    expect(childMoves(e4Node)).toContain('c5');
    expect(childMoves(e4Node)).toContain('e6');
    expect(childMoves(e4Node).length).toBe(3);
  });

  it('correctly sets move_number and is_white_move', () => {
    const tree = pgnToTree('1. e4 e5 2. Nf3');
    const e4 = tree.children![0];
    expect(e4.move_number).toBe(1);
    expect(e4.is_white_move).toBe(true);

    const e5 = e4.children![0];
    expect(e5.move_number).toBe(1);
    expect(e5.is_white_move).toBe(false);

    const nf3 = e5.children![0];
    expect(nf3.move_number).toBe(2);
    expect(nf3.is_white_move).toBe(true);
  });

  it('sets parent_id correctly', () => {
    const tree = pgnToTree('1. e4 e5 2. Nf3');
    const e4 = tree.children![0];
    expect(e4.parent_id).toBe(tree.id);

    const e5 = e4.children![0];
    expect(e5.parent_id).toBe(e4.id);
  });

  it('generates valid FENs', () => {
    const tree = pgnToTree('1. e4 e5 2. Nf3 Nc6');
    const e4 = tree.children![0];
    expect(e4.fen).toContain('4P3'); // pawn on e4
    expect(e4.fen).not.toBe(STARTING_FEN);
  });
});

describe('treeToPgn', () => {
  it('serializes a simple tree', () => {
    const tree = pgnToTree('1. e4 e5 2. Nf3 Nc6');
    const pgn = treeToPgn(tree);
    expect(pgn).toBe('1. e4 e5 2. Nf3 Nc6');
  });

  it('serializes empty tree', () => {
    const tree = pgnToTree('');
    const pgn = treeToPgn(tree);
    expect(pgn).toBe('*');
  });

  it('serializes tree with variation', () => {
    const tree = pgnToTree('1. e4 e5 2. Nf3 (2. Bc4) 2... Nc6');
    const pgn = treeToPgn(tree);
    // Should contain the variation in parentheses
    expect(pgn).toContain('Nf3');
    expect(pgn).toContain('(');
    expect(pgn).toContain('Bc4');
    expect(pgn).toContain(')');
    expect(pgn).toContain('Nc6');
  });

  it('roundtrips a simple game', () => {
    const original = '1. e4 e5 2. Nf3 Nc6 3. Bb5 a6';
    const tree = pgnToTree(original);
    const pgn = treeToPgn(tree);
    // Re-parse the output and compare main lines
    const tree2 = pgnToTree(pgn);
    expect(mainLineMoves(tree2)).toEqual(mainLineMoves(tree));
  });

  it('roundtrips a game with variations', () => {
    const original = '1. e4 e5 2. Nf3 (2. Bc4 Bc5) 2... Nc6';
    const tree = pgnToTree(original);
    const pgn = treeToPgn(tree);
    const tree2 = pgnToTree(pgn);

    // Main line should match
    expect(mainLineMoves(tree2)).toEqual(mainLineMoves(tree));

    // Variation should be preserved
    const e5Node = tree2.children![0].children![0];
    expect(childMoves(e5Node).length).toBe(2);
    expect(childMoves(e5Node)).toContain('Nf3');
    expect(childMoves(e5Node)).toContain('Bc4');
  });
});

describe('tree manipulation', () => {
  let tree: OpeningNode;

  beforeEach(() => {
    tree = pgnToTree('1. e4 e5 2. Nf3 Nc6');
  });

  describe('addMove', () => {
    it('adds a move as a child', () => {
      const nc6 = tree.children![0].children![0].children![0].children![0]; // e4>e5>Nf3>Nc6
      expect(nc6.move_san).toBe('Nc6');

      // Simulate adding Bb5 after Nc6
      const { Chess } = require('chess.js');
      const chess = new Chess(nc6.fen);
      const move = chess.move('Bb5');

      const newTree = cloneTree(tree);
      const parent = findNodeById(newTree, nc6.id)!;
      const newNode: OpeningNode = {
        id: 'test-new-node',
        repertoire_id: '',
        parent_id: parent.id,
        fen: chess.fen(),
        move_san: move.san,
        move_uci: move.from + move.to,
        move_number: 3,
        is_white_move: true,
        opening_name: null,
        eco_code: null,
        notes: null,
        priority: 1,
        is_critical: false,
        times_trained: 0,
        times_correct: 0,
        last_trained_at: null,
        next_review_at: null,
        ease_factor: 2.5,
        interval_days: 0,
        created_at: '',
        updated_at: '',
        children: [],
      };

      if (!parent.children) parent.children = [];
      parent.children.push(newNode);

      expect(mainLineMoves(newTree)).toEqual(['e4', 'e5', 'Nf3', 'Nc6', 'Bb5']);
    });

    it('creates a variation when parent already has a child', () => {
      const e5 = tree.children![0].children![0]; // e4>e5
      expect(e5.move_san).toBe('e5');

      // e5 already has Nf3 as child. Add Bc4 as variation.
      const { Chess } = require('chess.js');
      const chess = new Chess(e5.fen);
      const move = chess.move('Bc4');

      const newTree = cloneTree(tree);
      const parent = findNodeById(newTree, e5.id)!;
      const newNode: OpeningNode = {
        id: 'test-variation',
        repertoire_id: '',
        parent_id: parent.id,
        fen: chess.fen(),
        move_san: move.san,
        move_uci: move.from + move.to,
        move_number: 2,
        is_white_move: true,
        opening_name: null,
        eco_code: null,
        notes: null,
        priority: 1,
        is_critical: false,
        times_trained: 0,
        times_correct: 0,
        last_trained_at: null,
        next_review_at: null,
        ease_factor: 2.5,
        interval_days: 0,
        created_at: '',
        updated_at: '',
        children: [],
      };

      parent.children!.push(newNode);

      // Main line stays the same
      expect(mainLineMoves(newTree)).toEqual(['e4', 'e5', 'Nf3', 'Nc6']);

      // e5 now has 2 children
      expect(childMoves(parent)).toEqual(['Nf3', 'Bc4']);
    });
  });

  describe('deleteFromHere', () => {
    it('deletes a node and its descendants', () => {
      const nf3 = tree.children![0].children![0].children![0]; // e4>e5>Nf3
      expect(nf3.move_san).toBe('Nf3');

      const newTree = cloneTree(tree);
      const e5 = findNodeById(newTree, tree.children![0].children![0].id)!;
      const nf3Clone = e5.children![0];
      e5.children!.splice(e5.children!.indexOf(nf3Clone), 1);

      expect(mainLineMoves(newTree)).toEqual(['e4', 'e5']);
    });
  });

  describe('deleteVariation', () => {
    it('removes a variation (non-main-line child)', () => {
      // Build tree with variation
      const treeWithVar = pgnToTree('1. e4 e5 2. Nf3 (2. Bc4) 2... Nc6');
      const e5 = treeWithVar.children![0].children![0]; // e4>e5
      expect(childMoves(e5)).toEqual(['Nf3', 'Bc4']);

      const newTree = cloneTree(treeWithVar);
      const e5Clone = findNodeById(newTree, e5.id)!;
      const bc4 = e5Clone.children![1]; // Bc4 is the variation

      // Remove the variation
      e5Clone.children!.splice(1, 1);

      expect(childMoves(e5Clone)).toEqual(['Nf3']);
      expect(mainLineMoves(newTree)).toEqual(['e4', 'e5', 'Nf3', 'Nc6']);
    });

    it('does not remove the main line', () => {
      const treeWithVar = pgnToTree('1. e4 e5 2. Nf3 (2. Bc4) 2... Nc6');
      const e5 = treeWithVar.children![0].children![0];

      // Try to "delete variation" on the main line child (index 0)
      const parent = findParentOf(treeWithVar, e5.children![0].id);
      expect(parent).toBeTruthy();
      const idx = parent!.children!.findIndex(c => c.id === e5.children![0].id);
      expect(idx).toBe(0); // It's the main line, should not be deleted as a "variation"
    });
  });

  describe('promoteVariation', () => {
    it('swaps a variation to be the main line', () => {
      const treeWithVar = pgnToTree('1. e4 e5 2. Nf3 (2. Bc4) 2... Nc6');
      const e5 = treeWithVar.children![0].children![0];
      expect(childMoves(e5)).toEqual(['Nf3', 'Bc4']);

      const newTree = cloneTree(treeWithVar);
      const e5Clone = findNodeById(newTree, e5.id)!;

      // Promote Bc4
      const bc4 = e5Clone.children![1];
      const idx = e5Clone.children!.findIndex(c => c.id === bc4.id);
      const [variation] = e5Clone.children!.splice(idx, 1);
      e5Clone.children!.unshift(variation);

      expect(childMoves(e5Clone)).toEqual(['Bc4', 'Nf3']);
      // Main line now starts with Bc4
      expect(e5Clone.children![0].move_san).toBe('Bc4');
    });
  });

  describe('makeMainLine', () => {
    it('promotes a variation all the way up', () => {
      // Create a deeper tree: 1. e4 e5 (1... d5) 2. Nf3
      // If we make d5 the main line, it should become children[0] of root
      const deepTree = pgnToTree('1. e4 e5 (1... d5) 2. Nf3');
      const e4 = deepTree.children![0];
      expect(childMoves(e4)).toEqual(['e5', 'd5']);

      const newTree = cloneTree(deepTree);
      const e4Clone = findNodeById(newTree, e4.id)!;

      // Promote d5 to be main line
      const d5 = e4Clone.children![1];
      const idx = e4Clone.children!.findIndex(c => c.id === d5.id);
      const [variation] = e4Clone.children!.splice(idx, 1);
      e4Clone.children!.unshift(variation);

      expect(childMoves(e4Clone)).toEqual(['d5', 'e5']);
      expect(mainLineMoves(newTree)).toEqual(['e4', 'd5']);
    });
  });
});

describe('findNodeById', () => {
  it('finds the root', () => {
    const tree = pgnToTree('1. e4 e5');
    expect(findNodeById(tree, tree.id)).toBe(tree);
  });

  it('finds a deep node', () => {
    const tree = pgnToTree('1. e4 e5 2. Nf3');
    const nf3 = tree.children![0].children![0].children![0];
    const found = findNodeById(tree, nf3.id);
    expect(found).toBe(nf3);
    expect(found!.move_san).toBe('Nf3');
  });

  it('returns null for non-existent id', () => {
    const tree = pgnToTree('1. e4');
    expect(findNodeById(tree, 'nonexistent')).toBeNull();
  });
});

describe('findParentOf', () => {
  it('finds parent of a child', () => {
    const tree = pgnToTree('1. e4 e5');
    const e5 = tree.children![0].children![0];
    const parent = findParentOf(tree, e5.id);
    expect(parent).toBeTruthy();
    expect(parent!.move_san).toBe('e4');
  });

  it('finds root as parent of first-level child', () => {
    const tree = pgnToTree('1. e4');
    const e4 = tree.children![0];
    const parent = findParentOf(tree, e4.id);
    expect(parent).toBe(tree);
  });

  it('returns null for root', () => {
    const tree = pgnToTree('1. e4');
    expect(findParentOf(tree, tree.id)).toBeNull();
  });
});

describe('cloneTree', () => {
  it('creates a deep copy', () => {
    const tree = pgnToTree('1. e4 e5 2. Nf3');
    const clone = cloneTree(tree);

    expect(clone.id).toBe(tree.id);
    expect(clone).not.toBe(tree);
    expect(clone.children![0]).not.toBe(tree.children![0]);

    // Modifying clone should not affect original
    clone.children![0].move_san = 'd4';
    expect(tree.children![0].move_san).toBe('e4');
  });
});
