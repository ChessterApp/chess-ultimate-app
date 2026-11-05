import { describe, it, expect } from 'vitest';
import { pgnToTree } from '@/hooks/useGameMoveTree';
import type { OpeningNode } from '@/types/openingNode';
import {
  getForkOptions, resolveNextChild, followRememberedLine, rememberPath, forkArrowShapes,
  FORK_MAIN_COLOR, FORK_ALT_COLOR, MAX_FORK_ARROWS,
} from '../variationFork';

/** Follows the main line `plies` moves from the root. */
function mainAt(tree: OpeningNode, plies: number): OpeningNode {
  let n = tree;
  for (let i = 0; i < plies; i++) n = n.children![0];
  return n;
}

// Fork after 1.e4: Black has 1…e5 (main, 5 plies long) and 1…c5 (3 plies).
const BLACK_FORK = '1. e4 e5 (1... c5 2. Nf3 d6) 2. Nf3 Nc6 3. Bb5 a6 *';
// Fork at the root after 1.e4 e5: White has 2.Nf3 / 2.Bc4 / 2.Nc3.
const WHITE_FORK = '1. e4 e5 2. Nf3 (2. Bc4 Nf6) (2. Nc3) Nc6 3. Bb5 *';

describe('getForkOptions', () => {
  it('returns [] when the node has fewer than two continuations', () => {
    const tree = pgnToTree('1. e4 e5 2. Nf3 *');
    expect(getForkOptions(tree, tree.id)).toEqual([]);
    expect(getForkOptions(tree, mainAt(tree, 3).id)).toEqual([]);
    expect(getForkOptions(null, 'x')).toEqual([]);
    expect(getForkOptions(tree, 'missing')).toEqual([]);
  });

  it('lists two options in tree order with Black move labels, preview and line length', () => {
    const tree = pgnToTree(BLACK_FORK);
    const opts = getForkOptions(tree, mainAt(tree, 1).id);
    expect(opts).toHaveLength(2);
    expect(opts[0]).toMatchObject({
      index: 1, isMain: true, san: 'e5', moveLabel: '1…e5', from: 'e7', to: 'e5',
      previewSan: '2.Nf3 Nc6 3.Bb5 a6', lineLength: 5, color: FORK_MAIN_COLOR,
    });
    expect(opts[1]).toMatchObject({
      index: 2, isMain: false, san: 'c5', moveLabel: '1…c5', from: 'c7', to: 'c5',
      previewSan: '2.Nf3 d6', lineLength: 3, color: FORK_ALT_COLOR,
    });
    expect(opts[0].nodeId).toBe(mainAt(tree, 2).id);
  });

  it('lists three White options and numbers a Black-first preview with an ellipsis', () => {
    const tree = pgnToTree(WHITE_FORK);
    const opts = getForkOptions(tree, mainAt(tree, 2).id);
    expect(opts.map(o => [o.index, o.moveLabel, o.isMain])).toEqual([
      [1, '2.Nf3', true], [2, '2.Bc4', false], [3, '2.Nc3', false],
    ]);
    expect(opts[0].previewSan).toBe('2…Nc6 3.Bb5');
    expect(opts[1].previewSan).toBe('2…Nf6');
    expect(opts[2]).toMatchObject({ previewSan: '', lineLength: 1 });
  });

  it('caps the preview at four plies', () => {
    const tree = pgnToTree('1. e4 (1. d4) e5 2. Nf3 Nc6 3. Bb5 a6 4. Ba4 *');
    const [main] = getForkOptions(tree, tree.id);
    expect(main.previewSan).toBe('1…e5 2.Nf3 Nc6 3.Bb5');
    expect(main.lineLength).toBe(7);
  });
});

describe('fork memory', () => {
  it('resolves the remembered child, falling back to the main line', () => {
    const tree = pgnToTree(BLACK_FORK);
    const fork = mainAt(tree, 1);
    const alt = fork.children![1];
    expect(resolveNextChild(fork, {})!.id).toBe(fork.children![0].id);
    expect(resolveNextChild(fork, { [fork.id]: alt.id })!.id).toBe(alt.id);
    // A remembered child that was deleted no longer counts.
    expect(resolveNextChild(fork, { [fork.id]: 'gone' })!.id).toBe(fork.children![0].id);
    expect(resolveNextChild(mainAt(tree, 6), {})).toBeNull();
  });

  it('follows remembered branches to the end of the line', () => {
    const tree = pgnToTree(BLACK_FORK);
    const fork = mainAt(tree, 1);
    const alt = fork.children![1];
    expect(followRememberedLine(tree, {}).move_san).toBe('a6');
    expect(followRememberedLine(tree, { [fork.id]: alt.id }).move_san).toBe('d6');
  });

  it('remembers every fork on the path and keeps identity when unchanged', () => {
    const tree = pgnToTree('1. e4 (1. d4 d5 (1... Nf6 2. c4)) e5 *');
    const d4 = tree.children![1];
    const nf6 = d4.children![1];
    const c4 = nf6.children![0];
    const memory = rememberPath(tree, c4.id, {});
    expect(memory).toEqual({ [tree.id]: d4.id, [d4.id]: nf6.id });
    expect(rememberPath(tree, c4.id, memory)).toBe(memory);
    expect(rememberPath(tree, 'missing', memory)).toBe(memory);
    // Non-fork nodes on the path are not recorded.
    const plain = pgnToTree('1. e4 e5 *');
    const empty = {};
    expect(rememberPath(plain, mainAt(plain, 2).id, empty)).toBe(empty);
  });
});

describe('forkArrowShapes', () => {
  it('draws numbered arrows, main bolder, the highlighted one boldest', () => {
    const tree = pgnToTree(WHITE_FORK);
    const shapes = forkArrowShapes(getForkOptions(tree, mainAt(tree, 2).id), 2);
    expect(shapes).toEqual([
      { orig: 'g1', dest: 'f3', brush: 'forkMain', modifiers: { lineWidth: 9 }, label: { text: '1' } },
      { orig: 'f1', dest: 'c4', brush: 'forkAltActive', modifiers: { lineWidth: 12 }, label: { text: '2' } },
      { orig: 'b1', dest: 'c3', brush: 'forkAlt', modifiers: { lineWidth: 7 }, label: { text: '3' } },
    ]);
  });

  it(`caps at ${MAX_FORK_ARROWS} arrows and is empty without a fork`, () => {
    const tree = pgnToTree('1. e4 (1. d4) (1. c4) (1. Nf3) (1. g3) *');
    expect(forkArrowShapes(getForkOptions(tree, tree.id), 1)).toHaveLength(MAX_FORK_ARROWS);
    expect(forkArrowShapes([], 0)).toEqual([]);
  });
});
