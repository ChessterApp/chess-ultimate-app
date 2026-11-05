// @vitest-environment jsdom
//
// Fork picker (line preview list): one row per continuation, Main tag, row
// click enters that child, "+N more" past three rows. Real en messages so the
// ICU plurals are exercised.
import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, fireEvent, cleanup } from '@testing-library/react';
import React from 'react';
import { NextIntlClientProvider } from 'next-intl';
import messages from '../../../../messages/en.json';
import { pgnToTree } from '@/hooks/useGameMoveTree';
import { getForkOptions } from '@/lib/variationFork';
import VariationForkPicker from '../VariationForkPicker';

afterEach(() => cleanup());

function setup(pgn: string, highlightedIndex = 1) {
  const tree = pgnToTree(pgn);
  const fork = tree.children!.length > 1 ? tree : tree.children![0];
  const options = getForkOptions(tree, fork.id);
  const onSelect = vi.fn();
  render(
    <NextIntlClientProvider locale="en" messages={messages}>
      <VariationForkPicker
        options={options}
        highlightedIndex={highlightedIndex}
        turn={fork.fen.split(' ')[1] === 'b' ? 'black' : 'white'}
        onSelect={onSelect}
      />
    </NextIntlClientProvider>,
  );
  return { options, onSelect };
}

describe('VariationForkPicker', () => {
  it('renders a row per continuation with the Main tag, preview and length', () => {
    const { options } = setup('1. e4 e5 (1... c5 2. Nf3) 2. Nf3 Nc6 *');
    expect(screen.getByRole('group', { name: 'Black has 2 continuations' })).toBeTruthy();
    const main = screen.getByRole('button', { name: 'Continuation 1: 1…e5' });
    const alt = screen.getByRole('button', { name: 'Continuation 2: 1…c5' });
    expect(main.textContent).toContain('Main');
    expect(main.textContent).toContain('2.Nf3 Nc6');
    expect(main.textContent).toContain('3 moves ›');
    expect(alt.textContent).not.toContain('Main');
    expect(alt.textContent).toContain('2 moves ›');
    expect(main.getAttribute('aria-current')).toBe('true');
    expect(alt.getAttribute('aria-current')).toBeNull();
    expect(options).toHaveLength(2);
  });

  it('calls onSelect with the clicked continuation node id', () => {
    const { options, onSelect } = setup('1. e4 (1. d4 d5) (1. c4) *', 2);
    expect(screen.getByRole('group', { name: 'White has 3 continuations' })).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Continuation 2: 1.d4' }).getAttribute('aria-current')).toBe('true');
    fireEvent.click(screen.getByRole('button', { name: 'Continuation 3: 1.c4' }));
    expect(onSelect).toHaveBeenCalledWith(options[2].nodeId);
    expect(screen.queryByTestId('fork-more')).toBeNull();
  });

  it('shows three rows and a "+N more" row that expands the rest', () => {
    setup('1. e4 (1. d4) (1. c4) (1. Nf3) (1. g3) *');
    expect(screen.getAllByRole('button', { name: /^Continuation/ })).toHaveLength(3);
    fireEvent.click(screen.getByRole('button', { name: '+2 more' }));
    expect(screen.getAllByRole('button', { name: /^Continuation/ })).toHaveLength(5);
    expect(screen.queryByTestId('fork-more')).toBeNull();
  });

  it('keeps a highlight past the third row visible', () => {
    setup('1. e4 (1. d4) (1. c4) (1. Nf3) *', 4);
    expect(screen.getByRole('button', { name: 'Continuation 4: 1.Nf3' }).getAttribute('aria-current')).toBe('true');
  });

  it('renders nothing without a fork', () => {
    setup('1. e4 e5 *');
    expect(screen.queryByTestId('fork-picker')).toBeNull();
  });
});
