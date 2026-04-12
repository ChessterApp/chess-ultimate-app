/**
 * useGameMoveTree — Hook for editing a game's move tree (variations, promotions, deletions).
 * Only used for user-owned games (source === 'user').
 *
 * The tree node shape matches OpeningNode so MoveNotation can render it directly.
 */

import { useState, useCallback, useRef } from 'react';
import { Chess } from 'chess.js';
import type { OpeningNode } from '@/hooks/useOpeningRepertoire';

const STARTING_FEN = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1';

let _idCounter = 0;
function generateId(): string {
  return `gmt-${Date.now()}-${++_idCounter}-${Math.random().toString(36).slice(2, 6)}`;
}

function makeNode(overrides: Partial<OpeningNode> & { fen: string }): OpeningNode {
  const { fen, ...rest } = overrides;
  return {
    id: generateId(),
    repertoire_id: '',
    parent_id: null,
    fen,
    move_san: null,
    move_uci: null,
    move_number: 0,
    is_white_move: null,
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
    ...rest,
  };
}

// ── PGN → Tree ──────────────────────────────────────────────

export function pgnToTree(pgn: string): OpeningNode {
  const root = makeNode({ fen: STARTING_FEN });

  // Remove headers
  const moveText = pgn.replace(/\[.*?\]\s*/g, '').trim();
  if (!moveText || moveText === '*') return root;

  // Tokenize: move numbers, moves, variations (parentheses), results, comments
  const tokens = tokenize(moveText);
  buildTree(tokens, root, new Chess());
  return root;
}

function tokenize(text: string): string[] {
  const tokens: string[] = [];
  let i = 0;
  while (i < text.length) {
    // Skip whitespace
    if (/\s/.test(text[i])) { i++; continue; }

    // Comments in curly braces — skip
    if (text[i] === '{') {
      const end = text.indexOf('}', i);
      i = end === -1 ? text.length : end + 1;
      continue;
    }

    // Opening paren — variation start
    if (text[i] === '(') {
      tokens.push('(');
      i++;
      continue;
    }

    // Closing paren — variation end
    if (text[i] === ')') {
      tokens.push(')');
      i++;
      continue;
    }

    // Read a word token
    let word = '';
    while (i < text.length && !/[\s(){}]/.test(text[i])) {
      word += text[i];
      i++;
    }

    if (!word) continue;

    // Skip results
    if (['1-0', '0-1', '1/2-1/2', '*'].includes(word)) continue;

    // Skip move numbers (e.g. "1.", "1...", "12.")
    if (/^\d+\.+$/.test(word)) continue;

    // Skip NAGs like $1, $2
    if (/^\$\d+$/.test(word)) continue;

    tokens.push(word);
  }
  return tokens;
}

function buildTree(tokens: string[], parent: OpeningNode, chess: Chess): number {
  let i = 0;
  let currentParent = parent;

  while (i < tokens.length) {
    const token = tokens[i];

    if (token === ')') {
      return i + 1; // End of variation
    }

    if (token === '(') {
      // Start variation: fork from currentParent's parent (the position before the last main-line move)
      // The variation is an alternative to the last move added to currentParent's parent
      const variationParent = currentParent.parent_id
        ? findNodeById(parent, currentParent.parent_id) || parent
        : parent;

      // We need to find the actual parent in the root tree
      const rootAncestor = findRootAncestor(parent);
      const actualParent = findNodeById(rootAncestor, currentParent.parent_id || '') || parent;

      // Save chess state, rewind to variation parent position
      const savedFen = chess.fen();
      chess.load(actualParent.fen);

      i++; // skip '('
      const consumed = buildTree(tokens.slice(i), actualParent, chess);
      i += consumed;

      // Restore chess state
      chess.load(savedFen);
      continue;
    }

    // It's a move SAN
    try {
      const move = chess.move(token);
      if (move) {
        const fen = chess.fen();
        const fenParts = fen.split(' ');
        const isWhiteMove = fenParts[1] === 'b'; // after white's move, it's black's turn
        const moveNumber = parseInt(fenParts[5]) - (isWhiteMove ? 0 : 1);

        const node = makeNode({
          fen,
          move_san: move.san,
          move_uci: move.from + move.to + (move.promotion || ''),
          move_number: moveNumber || 1,
          is_white_move: isWhiteMove,
          parent_id: currentParent.id,
        });

        if (!currentParent.children) currentParent.children = [];
        currentParent.children.push(node);
        currentParent = node;
      }
    } catch {
      // Invalid move — skip
    }
    i++;
  }

  return i;
}

function findRootAncestor(node: OpeningNode): OpeningNode {
  // Walk up... but we don't have parent references, so just return the node
  // In our tree construction, the 'parent' param passed to buildTree IS the root for the top-level call
  return node;
}

function findNodeById(root: OpeningNode, id: string): OpeningNode | null {
  if (root.id === id) return root;
  for (const child of root.children || []) {
    const found = findNodeById(child, id);
    if (found) return found;
  }
  return null;
}

// ── Tree → PGN ──────────────────────────────────────────────

export function treeToPgn(root: OpeningNode): string {
  const parts: string[] = [];
  serializeLine(root.children || [], parts, true);
  const pgn = parts.join(' ').replace(/\s+/g, ' ').trim();
  return pgn || '*';
}

/**
 * Serialize a line of moves. `nodes` is the children array of the current position.
 * First child is the main line; subsequent children are variations.
 */
function serializeLine(nodes: OpeningNode[], parts: string[], forceNumber: boolean): void {
  if (nodes.length === 0) return;

  const main = nodes[0];
  emitMove(main, parts, forceNumber);

  // Variations (children[1..n] of the parent)
  for (let i = 1; i < nodes.length; i++) {
    parts.push('(');
    emitMove(nodes[i], parts, true);
    serializeLine(nodes[i].children || [], parts, false);
    parts.push(')');
  }

  // Continue main line
  serializeLine(main.children || [], parts, false);
}

function emitMove(node: OpeningNode, parts: string[], forceNumber: boolean): void {
  if (!node.move_san) return;

  if (node.is_white_move) {
    parts.push(`${node.move_number}.`);
    parts.push(node.move_san);
  } else if (forceNumber) {
    parts.push(`${node.move_number}...`);
    parts.push(node.move_san);
  } else {
    parts.push(node.move_san);
  }
}

// ── Deep clone ──────────────────────────────────────────────

function cloneTree(node: OpeningNode): OpeningNode {
  return {
    ...node,
    children: (node.children || []).map(cloneTree),
  };
}

// ── Hook ────────────────────────────────────────────────────

export function useGameMoveTree() {
  const [tree, setTree] = useState<OpeningNode | null>(null);
  const [isDirty, setIsDirty] = useState(false);
  const originalPgnRef = useRef<string>('');

  const initFromPgn = useCallback((pgn: string) => {
    originalPgnRef.current = pgn;
    const root = pgnToTree(pgn);
    setTree(root);
    setIsDirty(false);
  }, []);

  const addMove = useCallback((parentNodeId: string, san: string, uci: string, fen: string): OpeningNode | null => {
    if (!tree) return null;

    const fenParts = fen.split(' ');
    const isWhiteMove = fenParts[1] === 'b';
    const moveNumber = parseInt(fenParts[5]) - (isWhiteMove ? 0 : 1);

    const newNode = makeNode({
      fen,
      move_san: san,
      move_uci: uci,
      move_number: moveNumber || 1,
      is_white_move: isWhiteMove,
      parent_id: parentNodeId,
    });

    const newTree = cloneTree(tree);
    const parent = findNodeById(newTree, parentNodeId);
    if (!parent) return null;

    // Check if this move already exists as a child (by FEN position match)
    const fenKey = fen.split(' ').slice(0, 4).join(' ');
    const existing = (parent.children || []).find(
      c => c.fen.split(' ').slice(0, 4).join(' ') === fenKey
    );
    if (existing) return existing; // Navigate to existing

    if (!parent.children) parent.children = [];
    parent.children.push(newNode);
    setTree(newTree);
    setIsDirty(true);
    return newNode;
  }, [tree]);

  const deleteFromHere = useCallback((nodeId: string) => {
    if (!tree) return;
    const newTree = cloneTree(tree);
    removeNodeFromTree(newTree, nodeId);
    setTree(newTree);
    setIsDirty(true);
  }, [tree]);

  const deleteVariation = useCallback((nodeId: string) => {
    if (!tree) return;
    const newTree = cloneTree(tree);
    const parent = findParentOf(newTree, nodeId);
    if (!parent) return;

    // Only delete if it's not the main line (children[0])
    const idx = (parent.children || []).findIndex(c => c.id === nodeId);
    if (idx <= 0) return; // Can't delete main line as a "variation"

    parent.children!.splice(idx, 1);
    setTree(newTree);
    setIsDirty(true);
  }, [tree]);

  const promoteVariation = useCallback((nodeId: string) => {
    if (!tree) return;
    const newTree = cloneTree(tree);
    const parent = findParentOf(newTree, nodeId);
    if (!parent || !parent.children) return;

    const idx = parent.children.findIndex(c => c.id === nodeId);
    if (idx <= 0) return; // Already main line or not found

    // Swap with first child
    const [variation] = parent.children.splice(idx, 1);
    parent.children.unshift(variation);
    setTree(newTree);
    setIsDirty(true);
  }, [tree]);

  const makeMainLine = useCallback((nodeId: string) => {
    if (!tree) return;
    const newTree = cloneTree(tree);

    // Promote all the way up: from the target node to the root
    let currentId = nodeId;
    while (true) {
      const parent = findParentOf(newTree, currentId);
      if (!parent || !parent.children) break;

      const idx = parent.children.findIndex(c => c.id === currentId);
      if (idx <= 0) {
        // Already main line at this level; continue up
        currentId = parent.id;
        continue;
      }

      // Swap with first child
      const [variation] = parent.children.splice(idx, 1);
      parent.children.unshift(variation);
      currentId = parent.id;
    }

    setTree(newTree);
    setIsDirty(true);
  }, [tree]);

  const getPgn = useCallback((): string => {
    if (!tree) return '*';
    return treeToPgn(tree);
  }, [tree]);

  const markClean = useCallback(() => {
    setIsDirty(false);
  }, []);

  return {
    tree,
    setTree,
    isDirty,
    initFromPgn,
    addMove,
    deleteFromHere,
    deleteVariation,
    promoteVariation,
    makeMainLine,
    getPgn,
    markClean,
  };
}

// ── Helpers ─────────────────────────────────────────────────

function removeNodeFromTree(root: OpeningNode, nodeId: string): boolean {
  const children = root.children || [];
  for (let i = 0; i < children.length; i++) {
    if (children[i].id === nodeId) {
      children.splice(i, 1);
      return true;
    }
    if (removeNodeFromTree(children[i], nodeId)) return true;
  }
  return false;
}

function findParentOf(root: OpeningNode, nodeId: string): OpeningNode | null {
  for (const child of root.children || []) {
    if (child.id === nodeId) return root;
    const found = findParentOf(child, nodeId);
    if (found) return found;
  }
  return null;
}

// Re-export for tests
export { findNodeById, findParentOf, cloneTree };
