/**
 * Variation forks in a game move tree: a position with two or more recorded
 * continuations. Pure helpers behind the fork picker, the board arrows and
 * fork-aware Next / Go-to-end navigation.
 */
import type { DrawShape } from 'chessground/draw';
import type { Key } from 'chessground/types';
import type { OpeningNode } from '@/types/openingNode';

export const FORK_MAIN_COLOR = '#15803d';
export const FORK_ALT_COLOR = '#2563eb';
/** Most arrows drawn on the board at one fork. */
export const MAX_FORK_ARROWS = 4;
const PREVIEW_PLIES = 4;

/** Fork parent id → the child the user last entered from it. */
export type ForkMemory = Record<string, string>;

export interface ForkOption {
  nodeId: string;
  /** 1-based, in tree order; 1 is the main line. */
  index: number;
  isMain: boolean;
  san: string;
  /** e.g. "11…Ngf6" or "12.O-O-O". */
  moveLabel: string;
  from: string;
  to: string;
  /** The line's next few plies after this move, e.g. "12.O-O-O Be7 13.Kb1 O-O". */
  previewSan: string;
  /** Plies in this line, the move itself included, following main continuations to the end. */
  lineLength: number;
  color: string;
}

function findNode(root: OpeningNode, id: string): OpeningNode | null {
  if (root.id === id) return root;
  for (const c of root.children || []) {
    const f = findNode(c, id);
    if (f) return f;
  }
  return null;
}

/** Nodes from the root down to `id` (inclusive), or null when absent. */
function pathTo(root: OpeningNode, id: string): OpeningNode[] | null {
  if (root.id === id) return [root];
  for (const c of root.children || []) {
    const p = pathTo(c, id);
    if (p) return [root, ...p];
  }
  return null;
}

function moveNumberText(node: OpeningNode, first: boolean): string {
  if (node.is_white_move) return `${node.move_number}.`;
  return first ? `${node.move_number}…` : '';
}

function previewOf(node: OpeningNode): string {
  const parts: string[] = [];
  let cur = node.children?.[0];
  while (cur && parts.length < PREVIEW_PLIES) {
    parts.push(`${moveNumberText(cur, parts.length === 0)}${cur.move_san}`);
    cur = cur.children?.[0];
  }
  return parts.join(' ');
}

function lineLengthOf(node: OpeningNode): number {
  let n = 1;
  for (let cur = node.children?.[0]; cur; cur = cur.children?.[0]) n++;
  return n;
}

/** One option per continuation of `nodeId` — empty unless it is a fork. */
export function getForkOptions(tree: OpeningNode | null | undefined, nodeId: string | null | undefined): ForkOption[] {
  if (!tree) return [];
  const node = findNode(tree, nodeId ?? tree.id);
  const children = node?.children || [];
  if (children.length < 2) return [];
  return children.map((child, i) => ({
    nodeId: child.id,
    index: i + 1,
    isMain: i === 0,
    san: child.move_san ?? '',
    moveLabel: `${moveNumberText(child, true)}${child.move_san ?? ''}`,
    from: child.move_uci?.slice(0, 2) ?? '',
    to: child.move_uci?.slice(2, 4) ?? '',
    previewSan: previewOf(child),
    lineLength: lineLengthOf(child),
    color: i === 0 ? FORK_MAIN_COLOR : FORK_ALT_COLOR,
  }));
}

/** The continuation to play from `node`: the remembered child if still present, else the main line. */
export function resolveNextChild(node: OpeningNode, memory: ForkMemory): OpeningNode | null {
  const children = node.children || [];
  return children.find(c => c.id === memory[node.id]) ?? children[0] ?? null;
}

/** Last node reached from `node` by following remembered (else main) continuations. */
export function followRememberedLine(node: OpeningNode, memory: ForkMemory): OpeningNode {
  let cur = node;
  for (let next = resolveNextChild(cur, memory); next; next = resolveNextChild(cur, memory)) cur = next;
  return cur;
}

/**
 * Records, for every fork on the path to `nodeId`, which child the path takes.
 * Returns `memory` itself when nothing changes.
 */
export function rememberPath(tree: OpeningNode, nodeId: string, memory: ForkMemory): ForkMemory {
  const path = pathTo(tree, nodeId);
  if (!path) return memory;
  let next = memory;
  for (let i = 0; i < path.length - 1; i++) {
    const parent = path[i];
    if ((parent.children?.length ?? 0) < 2 || next[parent.id] === path[i + 1].id) continue;
    if (next === memory) next = { ...memory };
    next[parent.id] = path[i + 1].id;
  }
  return next;
}

/** chessground brushes for the fork arrows (alternates fade unless highlighted). */
export const FORK_BRUSHES = {
  forkMain: { key: 'forkMain', color: FORK_MAIN_COLOR, opacity: 0.9, lineWidth: 10 },
  forkAlt: { key: 'forkAlt', color: FORK_ALT_COLOR, opacity: 0.6, lineWidth: 10 },
  forkAltActive: { key: 'forkAltActive', color: FORK_ALT_COLOR, opacity: 0.9, lineWidth: 10 },
};

/** Numbered auto-shape arrows for the first MAX_FORK_ARROWS options; the highlighted one is boldest. */
export function forkArrowShapes(options: ForkOption[], highlightedIndex: number): DrawShape[] {
  return options
    .slice(0, MAX_FORK_ARROWS)
    .filter(o => o.from && o.to)
    .map(o => {
      const active = o.index === highlightedIndex;
      return {
        orig: o.from as Key,
        dest: o.to as Key,
        brush: o.isMain ? 'forkMain' : active ? 'forkAltActive' : 'forkAlt',
        modifiers: { lineWidth: active ? 12 : o.isMain ? 9 : 7 },
        label: { text: String(o.index) },
      };
    });
}
