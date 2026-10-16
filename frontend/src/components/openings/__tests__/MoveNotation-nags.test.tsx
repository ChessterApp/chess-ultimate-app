// @vitest-environment jsdom
//
// Move symbols (NAGs) in the editable notation: rendering next to the SAN,
// the context-menu palette, the toolbar popover and `!`/`?` typing.
import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, fireEvent, cleanup, act, within } from '@testing-library/react';
import React from 'react';
import MoveNotation from '../MoveNotation';
import { pgnToTree } from '@/hooks/useGameMoveTree';

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

function setup(pgn: string, opts: { onNagToggle?: ReturnType<typeof vi.fn>; selectFirst?: boolean } = {}) {
  const tree = pgnToTree(pgn);
  render(
    <MoveNotation
      tree={tree}
      selectedNodeId={opts.selectFirst ? tree.children![0].id : null}
      onNodeSelect={vi.fn()}
      loading={false}
      contextMenuActions={opts.onNagToggle ? {
        onNagToggle: opts.onNagToggle,
        onCommentChange: vi.fn(),
        labels: { moveSymbols: 'Move symbols', moreSymbols: 'More symbols…', fewerSymbols: 'Fewer symbols', nagNames: { brilliant: 'Brilliant move' } },
      } : undefined}
    />,
  );
  return tree;
}

describe('MoveNotation symbol rendering', () => {
  it('glues the move-quality symbol to the SAN and shows evaluation after it', () => {
    setup('1. Nf3 $3 $16 $146 $250 d5 $2');
    expect(screen.getByText('Nf3', { exact: false }).textContent).toBe('Nf3!! ± N');
    const qualities = screen.getAllByTestId('move-nag-quality');
    expect(qualities.map(q => q.textContent)).toEqual(['!!', '?']);
    expect(getComputedStyle(qualities[0]).color).toBe('rgb(38, 194, 163)');
    expect(getComputedStyle(qualities[1]).color).toBe('rgb(240, 140, 0)');
  });

  it('renders comments after symbols', () => {
    setup('1. e4 $1 {best}', { onNagToggle: vi.fn() });
    const san = screen.getByText('e4', { exact: false });
    const comment = screen.getByTestId('move-comment');
    expect(san.compareDocumentPosition(comment) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });
});

describe('MoveNotation context-menu palette', () => {
  it('applies a symbol and keeps the menu open', () => {
    const onNagToggle = vi.fn();
    const tree = setup('1. e4 e5', { onNagToggle });
    fireEvent.contextMenu(screen.getByText('e4'));
    fireEvent.click(screen.getByTestId('nag-chip-3'));
    expect(onNagToggle).toHaveBeenCalledWith(expect.objectContaining({ id: tree.children![0].id }), 3);
    expect(screen.getByTestId('nag-palette')).toBeTruthy();
    expect(screen.getByLabelText('Brilliant move')).toBeTruthy();
  });

  it('highlights active symbols and removes them on click', () => {
    const onNagToggle = vi.fn();
    setup('1. e4 $1 e5', { onNagToggle });
    fireEvent.contextMenu(screen.getByText('e4', { exact: false }));
    const chip = screen.getByTestId('nag-chip-1');
    expect(chip.getAttribute('aria-pressed')).toBe('true');
    expect(screen.getByTestId('nag-chip-2').getAttribute('aria-pressed')).toBe('false');
    fireEvent.click(chip);
    expect(onNagToggle.mock.calls[0][1]).toBe(1);
  });

  it('reveals the bonus row via "More symbols…"', () => {
    setup('1. e4', { onNagToggle: vi.fn() });
    fireEvent.contextMenu(screen.getByText('e4'));
    expect(screen.queryByTestId('nag-chip-146')).toBeNull();
    expect(screen.getAllByRole('button', { pressed: false }).length).toBe(15);
    fireEvent.click(screen.getByText('More symbols…'));
    expect(screen.getByTestId('nag-chip-146')).toBeTruthy();
    expect(screen.getByText('Fewer symbols')).toBeTruthy();
  });
});

describe('MoveNotation toolbar button', () => {
  it('is disabled without a selected move', () => {
    setup('1. e4', { onNagToggle: vi.fn() });
    expect((screen.getByLabelText('Move symbols') as HTMLButtonElement).disabled).toBe(true);
  });

  it('opens the palette for the selected move', () => {
    const onNagToggle = vi.fn();
    const tree = setup('1. e4', { onNagToggle, selectFirst: true });
    fireEvent.click(screen.getByLabelText('Move symbols'));
    const palette = screen.getByTestId('nag-palette');
    fireEvent.click(within(palette).getByTestId('nag-chip-10'));
    expect(onNagToggle).toHaveBeenCalledWith(expect.objectContaining({ id: tree.children![0].id }), 10);
  });

  it('is absent in read-only mode', () => {
    setup('1. e4');
    expect(screen.queryByLabelText('Move symbols')).toBeNull();
  });
});

describe('MoveNotation keyboard symbols', () => {
  it('combines `!` then `?` into !?', () => {
    vi.useFakeTimers();
    const onNagToggle = vi.fn();
    setup('1. e4', { onNagToggle, selectFirst: true });
    fireEvent.keyDown(window, { key: '!' });
    fireEvent.keyDown(window, { key: '?' });
    expect(onNagToggle).toHaveBeenCalledTimes(1);
    expect(onNagToggle.mock.calls[0][1]).toBe(5);
  });

  it('applies a single key after the buffer window', () => {
    vi.useFakeTimers();
    const onNagToggle = vi.fn();
    setup('1. e4', { onNagToggle, selectFirst: true });
    fireEvent.keyDown(window, { key: '?' });
    expect(onNagToggle).not.toHaveBeenCalled();
    act(() => { vi.advanceTimersByTime(400); });
    expect(onNagToggle.mock.calls[0][1]).toBe(2);
  });

  it('ignores keys typed into a text field or with no move selected', () => {
    vi.useFakeTimers();
    const onNagToggle = vi.fn();
    setup('1. e4', { onNagToggle });
    fireEvent.keyDown(window, { key: '!' });
    const input = document.createElement('input');
    document.body.appendChild(input);
    fireEvent.keyDown(input, { key: '!' });
    act(() => { vi.advanceTimersByTime(500); });
    expect(onNagToggle).not.toHaveBeenCalled();
    input.remove();
  });
});
