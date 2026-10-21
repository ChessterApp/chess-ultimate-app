// @vitest-environment jsdom
//
// Move actions in the editable notation: "Delete move" (top of the desktop
// menu, selects the previous move), the mobile bottom sheet (second tap or
// long-press) sharing the same action list, and the action bar pinned outside
// the scrolling move list.
import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest';
import { render, screen, fireEvent, cleanup, within, act } from '@testing-library/react';
import React, { useState } from 'react';
import MoveNotation, { type MoveContextMenuActions } from '../MoveNotation';
import { pgnToTree, findNodeById, useGameMoveTree } from '@/hooks/useGameMoveTree';
import type { OpeningNode } from '@/types/openingNode';

const LABELS: MoveContextMenuActions['labels'] = {
  deleteMove: 'Delete move',
  addComment: 'Add comment',
  editComment: 'Edit comment',
  commentPlaceholder: 'Comment',
  moveSymbols: 'Move symbols',
  makeMainLine: 'Make main line',
  promoteVariation: 'Promote variation',
  deleteVariation: 'Delete variation',
  comment: 'Comment',
  symbols: 'Symbols',
  more: 'More',
  moreActions: 'More actions',
  saveComment: 'Save',
  cancel: 'Cancel',
};

/** Mirrors the database page: an editable tree whose delete selects the previous move. */
function Harness({ pgn, initialSelected }: { pgn: string; initialSelected?: (t: OpeningNode) => string }) {
  const moveTree = useGameMoveTree();
  const [tree] = useState(() => pgnToTree(pgn));
  const [selected, setSelected] = useState<string | null>(() => (initialSelected ? initialSelected(tree) : null));
  if (!moveTree.tree) moveTree.setTree(tree);
  const live = moveTree.tree ?? tree;
  const selectedNode = selected ? findNodeById(live, selected) : null;
  return (
    <>
      <div data-testid="selected">{selectedNode?.move_san ?? 'root'}</div>
      <MoveNotation
        tree={live}
        selectedNodeId={selected}
        onNodeSelect={(n) => setSelected(n.id)}
        loading={false}
        contextMenuActions={{
          onDeleteMove: (node) => {
            const parentId = moveTree.deleteFromHere(node.id);
            if (parentId) setSelected(parentId);
          },
          onDeleteVariation: vi.fn(),
          onPromoteVariation: vi.fn(),
          onMakeMainLine: vi.fn(),
          onCommentChange: (node, text) => moveTree.setComment(node.id, text),
          onNagToggle: (node, code) => moveTree.toggleNag(node.id, code),
          labels: LABELS,
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
      matches,
      media: query,
      onchange: null,
      addListener: () => {},
      removeListener: () => {},
      addEventListener: () => {},
      removeEventListener: () => {},
      dispatchEvent: () => false,
    }),
  });
}

function move(san: string) {
  return within(screen.getByTestId('move-notation-scroll')).getByText(san, { exact: true });
}

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  // @ts-expect-error — restore jsdom's default (no matchMedia)
  delete window.matchMedia;
});

describe('Delete move (desktop menu)', () => {
  it('is the first item of the move menu', () => {
    render(<Harness pgn="1. e4 e5 2. Nf3" />);
    fireEvent.contextMenu(move('e5'));
    const items = screen.getAllByRole('menuitem');
    expect(items[0].textContent).toBe('Delete move');
  });

  it('deletes a main-line move with its continuation and selects the previous move', () => {
    render(<Harness pgn="1. e4 e5 2. Nf3 Nc6" initialSelected={t => t.children![0].children![0].children![0].children![0].id} />);
    fireEvent.contextMenu(move('Nf3'));
    fireEvent.click(screen.getByText('Delete move'));
    expect(screen.queryByText('Nf3')).toBeNull();
    expect(screen.queryByText('Nc6')).toBeNull();
    expect(screen.getByTestId('selected').textContent).toBe('e5');
  });

  it('deletes a variation move and selects the previous move in that variation', () => {
    render(<Harness pgn="1. e4 e5 2. Nf3 (2. Bc4 Bc5) 2... Nc6" />);
    fireEvent.contextMenu(move('Bc5'));
    fireEvent.click(screen.getByText('Delete move'));
    expect(screen.queryByText('Bc5')).toBeNull();
    expect(screen.getByTestId('selected').textContent).toBe('Bc4');

    fireEvent.contextMenu(move('Bc4'));
    fireEvent.click(screen.getByText('Delete move'));
    expect(screen.queryByText('Bc4')).toBeNull();
    expect(screen.getByTestId('selected').textContent).toBe('e5');
    // The main line is untouched.
    expect(move('Nf3')).toBeTruthy();
    expect(move('Nc6')).toBeTruthy();
  });
});

describe('Action bar', () => {
  it('is rendered outside the scrolling move list', () => {
    render(<Harness pgn="1. e4 e5" />);
    const scroll = screen.getByTestId('move-notation-scroll');
    const bar = screen.getByTestId('move-action-bar');
    expect(scroll.contains(bar)).toBe(false);
    expect(within(bar).getByLabelText('Add comment')).toBeTruthy();
    expect(within(bar).getByLabelText('Move symbols')).toBeTruthy();
    expect(within(bar).getByLabelText('More actions')).toBeTruthy();
  });

  it('move list packs wrapped lines at the top instead of stretching them over the panel', () => {
    render(<Harness pgn="1. e4 e5 2. Nf3 Nc6 3. Bb5" />);
    const scroll = screen.getByTestId('move-notation-scroll');
    expect(getComputedStyle(scroll).alignContent).toBe('flex-start');
  });

  it('"More" opens the move menu for the selected move on desktop', () => {
    render(<Harness pgn="1. e4 e5" initialSelected={t => t.children![0].id} />);
    fireEvent.click(screen.getByLabelText('More actions'));
    fireEvent.click(screen.getByText('Delete move'));
    expect(screen.getByTestId('selected').textContent).toBe('root');
    expect(screen.queryByText('e4')).toBeNull();
  });
});

describe('Mobile action sheet', () => {
  beforeEach(() => mockMatchMedia(true));

  it('shows text labels in the action bar', () => {
    render(<Harness pgn="1. e4 e5" initialSelected={t => t.children![0].id} />);
    const bar = screen.getByTestId('move-action-bar');
    expect(within(bar).getByText('Comment')).toBeTruthy();
    expect(within(bar).getByText('Symbols')).toBeTruthy();
    expect(within(bar).getByText('More')).toBeTruthy();
  });

  it('first tap selects, second tap on the selected move opens the sheet', () => {
    render(<Harness pgn="1. e4 e5" />);
    fireEvent.click(move('e5'));
    expect(screen.getByTestId('selected').textContent).toBe('e5');
    expect(screen.queryByTestId('move-action-sheet')).toBeNull();

    fireEvent.click(move('e5'));
    const sheet = screen.getByTestId('move-action-sheet');
    const rows = within(sheet).getAllByRole('menuitem').map(r => r.textContent);
    expect(rows).toEqual(['Add comment', '!?Move symbols', 'Delete move']);
  });

  it('long-press opens the sheet for that move', () => {
    vi.useFakeTimers();
    render(<Harness pgn="1. e4 e5" />);
    fireEvent.touchStart(move('e4'));
    act(() => { vi.advanceTimersByTime(450); });
    fireEvent.touchEnd(move('e4'));
    expect(screen.getByTestId('move-action-sheet')).toBeTruthy();
    expect(screen.getByTestId('selected').textContent).toBe('e4');
  });

  it('a short tap or a released-early press does not open the sheet', () => {
    vi.useFakeTimers();
    render(<Harness pgn="1. e4 e5" />);
    fireEvent.touchStart(move('e4'));
    act(() => { vi.advanceTimersByTime(200); });
    fireEvent.touchEnd(move('e4'));
    act(() => { vi.advanceTimersByTime(500); });
    expect(screen.queryByTestId('move-action-sheet')).toBeNull();
  });

  it('cancels the long-press when the press is cancelled (scroll)', () => {
    vi.useFakeTimers();
    render(<Harness pgn="1. e4 e5" />);
    fireEvent.touchStart(move('e4'));
    fireEvent.touchCancel(move('e4'));
    act(() => { vi.advanceTimersByTime(600); });
    fireEvent.touchEnd(move('e4'));
    expect(screen.queryByTestId('move-action-sheet')).toBeNull();
  });

  it('variation moves get the variation actions', () => {
    render(<Harness pgn="1. e4 e5 2. Nf3 (2. Bc4) 2... Nc6" initialSelected={t => t.children![0].children![0].children![1].id} />);
    fireEvent.click(move('Bc4'));
    const sheet = screen.getByTestId('move-action-sheet');
    const rows = within(sheet).getAllByRole('menuitem').map(r => r.textContent);
    expect(rows).toEqual([
      'Add comment', '!?Move symbols', 'Make main line', 'Promote variation', 'Delete variation', 'Delete move',
    ]);
  });

  it('Delete move from the sheet selects the previous move', () => {
    render(<Harness pgn="1. e4 e5 2. Nf3" initialSelected={t => t.children![0].children![0].children![0].id} />);
    fireEvent.click(move('Nf3'));
    fireEvent.click(within(screen.getByTestId('move-action-sheet')).getByText('Delete move'));
    expect(screen.queryByText('Nf3')).toBeNull();
    expect(screen.getByTestId('selected').textContent).toBe('e5');
  });

  it('edits a comment in a sheet with Save / Cancel', () => {
    render(<Harness pgn="1. e4 e5" initialSelected={t => t.children![0].id} />);
    fireEvent.click(within(screen.getByTestId('move-action-bar')).getByText('Comment'));
    expect(screen.queryByTestId('move-comment-input')).toBeNull(); // no tiny inline field
    const input = screen.getByTestId('move-comment-sheet-input');
    fireEvent.change(input, { target: { value: 'king pawn' } });
    fireEvent.click(screen.getByText('Save'));
    expect(screen.getByTestId('move-comment').textContent).toBe('king pawn');
  });

  it('opens the symbol palette in the sheet', () => {
    render(<Harness pgn="1. e4" initialSelected={t => t.children![0].id} />);
    fireEvent.click(within(screen.getByTestId('move-action-bar')).getByText('Symbols'));
    const sheet = screen.getByTestId('move-action-sheet');
    fireEvent.click(within(sheet).getByTestId('nag-chip-1'));
    expect(move('e4').textContent).toBe('e4!');
  });
});
