// @vitest-environment jsdom
//
// Inline commentary in the editable notation: comments render after their move,
// click-to-edit in place, Enter/blur saves, Escape cancels. Read-only notation
// (no onCommentChange) never shows comments.
import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, fireEvent, cleanup } from '@testing-library/react';
import React from 'react';
import MoveNotation from '../MoveNotation';
import { pgnToTree } from '@/hooks/useGameMoveTree';

afterEach(() => cleanup());

function setup(pgn: string, onCommentChange?: ReturnType<typeof vi.fn>, selected?: (t: ReturnType<typeof pgnToTree>) => string) {
  const tree = pgnToTree(pgn);
  render(
    <MoveNotation
      tree={tree}
      selectedNodeId={selected ? selected(tree) : null}
      onNodeSelect={vi.fn()}
      loading={false}
      contextMenuActions={onCommentChange ? { onCommentChange, labels: { addComment: 'Add comment', commentPlaceholder: 'Comment' } } : undefined}
    />,
  );
  return tree;
}

describe('MoveNotation inline comments', () => {
  it('renders comments inline in edit mode', () => {
    setup('1. e4 {central} e5', vi.fn());
    expect(screen.getByTestId('move-comment').textContent).toBe('central');
  });

  it('hides comments in read-only mode', () => {
    setup('1. e4 {central} e5');
    expect(screen.queryByTestId('move-comment')).toBeNull();
  });

  it('edits a comment in place and saves on Enter', () => {
    const onCommentChange = vi.fn();
    const tree = setup('1. e4 {central} e5', onCommentChange);
    fireEvent.click(screen.getByTestId('move-comment'));
    const input = screen.getByTestId('move-comment-input') as HTMLInputElement;
    fireEvent.change(input, { target: { value: 'controls d5' } });
    fireEvent.keyDown(input, { key: 'Enter' });
    expect(onCommentChange).toHaveBeenCalledTimes(1);
    expect(onCommentChange.mock.calls[0][0].id).toBe(tree.children![0].id);
    expect(onCommentChange.mock.calls[0][1]).toBe('controls d5');
    expect(screen.queryByTestId('move-comment-input')).toBeNull();
  });

  it('cancels on Escape without saving', () => {
    const onCommentChange = vi.fn();
    setup('1. e4 {central}', onCommentChange);
    fireEvent.click(screen.getByTestId('move-comment'));
    const input = screen.getByTestId('move-comment-input');
    fireEvent.change(input, { target: { value: 'changed' } });
    fireEvent.keyDown(input, { key: 'Escape' });
    expect(onCommentChange).not.toHaveBeenCalled();
    expect(screen.getByTestId('move-comment').textContent).toBe('central');
  });

  it('adds a comment to the selected move and saves on blur', () => {
    const onCommentChange = vi.fn();
    const tree = setup('1. e4 e5', onCommentChange, t => t.children![0].children![0].id);
    fireEvent.click(screen.getByLabelText('Add comment'));
    const input = screen.getByTestId('move-comment-input');
    fireEvent.change(input, { target: { value: 'symmetric' } });
    fireEvent.blur(input);
    expect(onCommentChange).toHaveBeenCalledTimes(1);
    expect(onCommentChange.mock.calls[0][0].id).toBe(tree.children![0].children![0].id);
    expect(onCommentChange.mock.calls[0][1]).toBe('symmetric');
  });
});

describe('MoveNotation context menu comment item', () => {
  it('opens the inline editor from the move context menu', async () => {
    const onCommentChange = vi.fn();
    setup('1. e4 e5', onCommentChange);
    fireEvent.contextMenu(screen.getByText('e4'));
    fireEvent.click(screen.getByText('Add comment'));
    const input = await screen.findByTestId('move-comment-input');
    expect(document.activeElement).toBe(input);
    fireEvent.change(input, { target: { value: 'open game' } });
    fireEvent.keyDown(input, { key: 'Enter' });
    expect(onCommentChange.mock.calls[0][1]).toBe('open game');
  });
});
