/** @vitest-environment jsdom */
import { describe, it, expect, afterEach, vi } from 'vitest';
import { render, screen, cleanup, fireEvent } from '@testing-library/react';
import Wheel from '../Wheel';
import type { WheelSegment } from '@/lib/wheel/types';

// The CSS import in Wheel.tsx is harmless under jsdom, but stub matchMedia gaps.
afterEach(cleanup);

function makeSegments(n: number): WheelSegment[] {
  return Array.from({ length: n }, (_, i) => ({
    id: `s${i}`,
    label: `Prize ${i}`,
    color: i % 2 === 0 ? '#c62828' : '#f5efe0',
    emoji: i === 0 ? '🎁' : undefined,
  }));
}

function renderWheel(n: number, overrides: Partial<React.ComponentProps<typeof Wheel>> = {}) {
  const onSpin = vi.fn();
  const utils = render(
    <Wheel
      segments={makeSegments(n)}
      rotation={0}
      spinning={false}
      spinDurationMs={5000}
      spinLabel="SPIN"
      disabled={false}
      onSpin={onSpin}
      {...overrides}
    />,
  );
  return { onSpin, ...utils };
}

describe('Wheel', () => {
  it('renders one wedge per segment for various counts', () => {
    for (const n of [6, 12, 30]) {
      const { unmount } = renderWheel(n);
      expect(screen.getAllByTestId('wheel-segment')).toHaveLength(n);
      unmount();
    }
  });

  it('renders each segment label (with emoji when present)', () => {
    renderWheel(3);
    expect(screen.getByText('🎁 Prize 0')).toBeTruthy();
    expect(screen.getByText('Prize 1')).toBeTruthy();
    expect(screen.getByText('Prize 2')).toBeTruthy();
  });

  it('applies the rotation transform to the disc', () => {
    renderWheel(6, { rotation: 123 });
    const disc = screen.getByTestId('wheel-disc');
    expect(disc.style.transform).toBe('rotate(123deg)');
  });

  it('fires onSpin when the center button is clicked', () => {
    const { onSpin } = renderWheel(6);
    fireEvent.click(screen.getByRole('button', { name: 'SPIN' }));
    expect(onSpin).toHaveBeenCalledTimes(1);
  });

  it('disables the spin button while spinning', () => {
    renderWheel(6, { disabled: true, spinning: true });
    const btn = screen.getByRole('button');
    expect((btn as HTMLButtonElement).disabled).toBe(true);
  });

  it('uses a smaller label font for more segments', () => {
    const { container: few } = render(
      <Wheel segments={makeSegments(6)} rotation={0} spinning={false} spinDurationMs={5000} spinLabel="S" disabled={false} onSpin={() => {}} />,
    );
    const fewSize = few.querySelector('text')?.getAttribute('font-size');
    cleanup();
    const { container: many } = render(
      <Wheel segments={makeSegments(30)} rotation={0} spinning={false} spinDurationMs={5000} spinLabel="S" disabled={false} onSpin={() => {}} />,
    );
    const manySize = many.querySelector('text')?.getAttribute('font-size');
    expect(Number(fewSize)).toBeGreaterThan(Number(manySize));
  });
});
