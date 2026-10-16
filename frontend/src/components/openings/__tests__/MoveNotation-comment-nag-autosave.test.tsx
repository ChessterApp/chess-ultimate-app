// @vitest-environment jsdom
//
// Comments and move symbols on an own game: tapping a comment opens it for
// editing (inline on desktop, the bottom sheet on mobile), "Delete comment"
// clears it, a highlighted symbol in the picker removes it on tap — and every
// one of those edits reaches auto-save, wired exactly like the database page
// (useGameMoveTree → treeAutoSaveEntry → useAutoSave).
import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest';
import { render, screen, fireEvent, cleanup, within, act } from '@testing-library/react';
import React, { useEffect, useState } from 'react';
import MoveNotation from '../MoveNotation';
import { useGameMoveTree, findNodeById } from '@/hooks/useGameMoveTree';
import { treeAutoSaveEntry, type TreeSnapshot } from '../saveGameTree';
import { useAutoSave } from '../useAutoSave';
import type { OpenedGame } from '../GameViewerPanel';

const START = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1';
const GAME: OpenedGame = {
  id: 'g-1', white: 'A', black: 'B', result: '*', pgn: '', moves: [], fens: [], startingFen: START, source: 'user',
};

function Harness({ pgn, save, selectFirst = false, readOnly = false }: {
  pgn: string;
  save: (s: TreeSnapshot) => Promise<boolean>;
  selectFirst?: boolean;
  readOnly?: boolean;
}) {
  const moveTree = useGameMoveTree();
  const [selected, setSelected] = useState<string | null>(null);
  const { tree, initFromPgn } = moveTree;
  useEffect(() => { initFromPgn(pgn); }, [initFromPgn, pgn]);
  useEffect(() => {
    if (selectFirst && tree?.children?.[0] && !selected) setSelected(tree.children[0].id);
  }, [selectFirst, tree, selected]);

  const entry = tree
    ? treeAutoSaveEntry(GAME, moveTree.getPgn(), { hasMoves: !!tree.children?.length, isDirty: moveTree.isDirty })
    : null;
  useAutoSave({ scope: GAME.id, entry, save, onClean: moveTree.markClean });

  const node = tree && selected ? findNodeById(tree, selected) : null;
  return (
    <>
      <div data-testid="nags">{(node?.nags ?? []).join(',')}</div>
      <MoveNotation
        tree={tree}
        selectedNodeId={selected}
        onNodeSelect={(n) => setSelected(n.id)}
        loading={false}
        showComments
        contextMenuActions={readOnly ? undefined : {
          onCommentChange: (n, text) => moveTree.setComment(n.id, text),
          onNagToggle: (n, code) => moveTree.toggleNag(n.id, code),
          labels: {
            deleteComment: 'Delete comment',
            commentPlaceholder: 'Comment',
            moveSymbols: 'Move symbols',
            symbols: 'Symbols',
            saveComment: 'Save',
            cancel: 'Cancel',
            nagNames: { good: 'Good move' },
          },
        }}
      />
    </>
  );
}

function mockMatchMedia(matches: boolean) {
  Object.defineProperty(window, 'matchMedia', {
    configurable: true,
    writable: true,
    value: (query: string) => ({
      matches, media: query, onchange: null,
      addListener: () => {}, removeListener: () => {},
      addEventListener: () => {}, removeEventListener: () => {}, dispatchEvent: () => false,
    }),
  });
}

async function flushAutoSave() {
  await act(async () => { vi.advanceTimersByTime(1600); });
  await act(async () => {});
}

let save: ReturnType<typeof vi.fn>;

beforeEach(() => {
  vi.useFakeTimers();
  save = vi.fn().mockResolvedValue(true);
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  // @ts-expect-error — restore jsdom's default (no matchMedia)
  delete window.matchMedia;
});

describe('Comments — tap to edit, Delete comment, auto-save', () => {
  it('desktop: tapping a comment opens the inline editor; Delete comment clears it and auto-saves', async () => {
    render(<Harness pgn="1. e4 {King pawn} e5" save={save} />);
    fireEvent.click(screen.getByText('King pawn'));
    expect((screen.getByTestId('move-comment-input') as HTMLInputElement).value).toBe('King pawn');

    fireEvent.click(screen.getByRole('button', { name: 'Delete comment' }));
    expect(screen.queryByText('King pawn')).toBeNull();
    expect(screen.queryByTestId('move-comment-input')).toBeNull();

    await flushAutoSave();
    expect(save).toHaveBeenCalledTimes(1);
    expect(save.mock.calls[0][0].pgn).toBe('1. e4 e5');
  });

  it('desktop: an edited comment auto-saves', async () => {
    render(<Harness pgn="1. e4 {King pawn} e5" save={save} />);
    fireEvent.click(screen.getByText('King pawn'));
    const input = screen.getByTestId('move-comment-input');
    fireEvent.change(input, { target: { value: 'Best by test' } });
    fireEvent.keyDown(input, { key: 'Enter' });
    await flushAutoSave();
    expect(save.mock.calls[0][0].pgn).toBe('1. e4 {Best by test} 1... e5');
  });

  it('mobile: tapping a comment opens the comment sheet; Delete comment clears it and auto-saves', async () => {
    mockMatchMedia(true);
    render(<Harness pgn="1. e4 {King pawn} e5" save={save} />);
    fireEvent.click(screen.getByText('King pawn'));
    const sheet = screen.getByTestId('move-action-sheet');
    expect((within(sheet).getByTestId('move-comment-sheet-input') as HTMLTextAreaElement).value).toBe('King pawn');

    fireEvent.click(within(sheet).getByRole('button', { name: 'Delete comment' }));
    expect(screen.queryByText('King pawn')).toBeNull();

    await flushAutoSave();
    expect(save.mock.calls[0][0].pgn).toBe('1. e4 e5');
  });

  it('offers no Delete comment while adding a new comment', () => {
    render(<Harness pgn="1. e4 e5" save={save} selectFirst />);
    fireEvent.click(screen.getByLabelText('Add comment'));
    expect(screen.getByTestId('move-comment-input')).toBeTruthy();
    expect(screen.queryByRole('button', { name: 'Delete comment' })).toBeNull();
  });

  it('read-only: comments show but are not editable and there is no action bar', () => {
    render(<Harness pgn="1. e4 {King pawn} e5" save={save} readOnly />);
    fireEvent.click(screen.getByText('King pawn'));
    expect(screen.queryByTestId('move-comment-input')).toBeNull();
    expect(screen.queryByTestId('move-action-bar')).toBeNull();
    expect(screen.queryByRole('button', { name: 'Delete comment' })).toBeNull();
  });
});

describe('Move symbols — highlighted symbol removes on tap, auto-saves', () => {
  it('desktop picker highlights the move\'s symbol; tapping it removes it', async () => {
    render(<Harness pgn="1. e4 $1 e5" save={save} selectFirst />);
    fireEvent.click(screen.getByLabelText('Move symbols'));
    const chip = screen.getByTestId('nag-chip-1');
    expect(chip.getAttribute('aria-pressed')).toBe('true');
    expect(screen.getByTestId('nag-chip-2').getAttribute('aria-pressed')).toBe('false');

    fireEvent.click(chip);
    expect(screen.getByTestId('nags').textContent).toBe('');
    expect(screen.getByTestId('nag-chip-1').getAttribute('aria-pressed')).toBe('false');

    await flushAutoSave();
    expect(save.mock.calls[0][0].pgn).toBe('1. e4 e5');
  });

  it('mobile sheet picker removes a highlighted symbol too', async () => {
    mockMatchMedia(true);
    render(<Harness pgn="1. e4 $1 e5" save={save} selectFirst />);
    fireEvent.click(screen.getByLabelText('Symbols'));
    const sheet = screen.getByTestId('move-action-sheet');
    const chip = within(sheet).getByTestId('nag-chip-1');
    expect(chip.getAttribute('aria-pressed')).toBe('true');
    fireEvent.click(chip);
    expect(screen.getByTestId('nags').textContent).toBe('');
    await flushAutoSave();
    expect(save.mock.calls[0][0].pgn).toBe('1. e4 e5');
  });
});
