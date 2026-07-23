// @vitest-environment jsdom
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import React from 'react';
import PromotionOverlay from '../PromotionOverlay';

function renderOverlay(overrides: Partial<React.ComponentProps<typeof PromotionOverlay>> = {}) {
  const onSelect = vi.fn();
  const onCancel = vi.fn();
  render(
    <PromotionOverlay
      to="e8"
      color="white"
      orientation="white"
      boardSize={480}
      onSelect={onSelect}
      onCancel={onCancel}
      {...overrides}
    />
  );
  return { onSelect, onCancel };
}

describe('PromotionOverlay', () => {
  it('renders a choice for every promotable piece', () => {
    renderOverlay();
    for (const role of ['q', 'r', 'b', 'n']) {
      expect(screen.getByTestId(`promotion-${role}`)).toBeTruthy();
    }
  });

  it('renders white Fritz sprites when white is promoting', () => {
    renderOverlay({ color: 'white' });
    for (const [role, sprite] of [
      ['q', 'wQ'],
      ['r', 'wR'],
      ['b', 'wB'],
      ['n', 'wN'],
    ] as const) {
      const img = screen.getByTestId(`promotion-${role}`).querySelector('img');
      expect(img).toBeTruthy();
      expect(img!.getAttribute('src')).toBe(`/static/pieces/Fritz/${sprite}.svg`);
    }
  });

  it('renders black Fritz sprites when black is promoting', () => {
    renderOverlay({ color: 'black', to: 'e1' });
    for (const [role, sprite] of [
      ['q', 'bQ'],
      ['r', 'bR'],
      ['b', 'bB'],
      ['n', 'bN'],
    ] as const) {
      const img = screen.getByTestId(`promotion-${role}`).querySelector('img');
      expect(img).toBeTruthy();
      expect(img!.getAttribute('src')).toBe(`/static/pieces/Fritz/${sprite}.svg`);
    }
  });

  it('reports the picked piece when knight is chosen', () => {
    const { onSelect, onCancel } = renderOverlay();
    fireEvent.click(screen.getByTestId('promotion-n'));
    expect(onSelect).toHaveBeenCalledWith('n');
    expect(onCancel).not.toHaveBeenCalled();
  });

  it('cancels when the backdrop is clicked', () => {
    const { onSelect, onCancel } = renderOverlay();
    fireEvent.click(screen.getByTestId('promotion-overlay'));
    expect(onCancel).toHaveBeenCalledTimes(1);
    expect(onSelect).not.toHaveBeenCalled();
  });
});
