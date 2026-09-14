/** @vitest-environment jsdom */
import { createRef } from 'react';
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { describe, it, expect, afterEach, vi } from 'vitest';
import { render, screen, cleanup, fireEvent } from '@testing-library/react';
import Wheel from '../Wheel';
import type { WheelSegment } from '@/lib/wheel/types';

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
      spinning={false}
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

  it('renders each segment label (with emoji rendered separately when present)', () => {
    renderWheel(3);
    // Emoji and label are drawn as separate <text> elements (emoji enlarged).
    expect(screen.getByText('🎁')).toBeTruthy();
    expect(screen.getByText('Prize 0')).toBeTruthy();
    expect(screen.getByText('Prize 1')).toBeTruthy();
    expect(screen.getByText('Prize 2')).toBeTruthy();
  });

  it('forwards discRef to the rotating disc so the physics driver can drive it', () => {
    const ref = createRef<HTMLDivElement>();
    renderWheel(6, { discRef: ref });
    expect(ref.current).toBe(screen.getByTestId('wheel-disc'));
    // The disc carries no inline transform: the driver writes it at runtime.
    expect(ref.current!.style.transform).toBe('');
  });

  it('does not put a CSS transition on the disc (JS drives every frame)', () => {
    renderWheel(6, { spinning: true });
    const disc = screen.getByTestId('wheel-disc');
    // No inline transition and no --spin-ms escape-hatch custom property.
    expect(disc.style.transition).toBe('');
    expect(disc.style.transitionDuration).toBe('');
    expect(disc.style.getPropertyValue('--spin-ms')).toBe('');
  });

  it('marks the stage as spinning to drive the decorative bulb chase', () => {
    const { rerender } = renderWheel(6, { spinning: false });
    expect(screen.getByTestId('wheel-stage').className).not.toContain('is-spinning');
    rerender(
      <Wheel segments={makeSegments(6)} spinning spinLabel="SPIN" disabled onSpin={() => {}} />,
    );
    expect(screen.getByTestId('wheel-stage').className).toContain('is-spinning');
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

  it('has no disc CSS transition to fight the JS-driven rotation', () => {
    const cssPath = path.resolve(process.cwd(), 'src/components/wheel/wheel.css');
    const css = readFileSync(cssPath, 'utf8');
    // The old model transitioned `transform` on .wheel-disc; the physics engine
    // now owns the disc angle, so there must be no transition on the disc.
    expect(css).not.toMatch(/\.wheel-disc[^{]*\{[^}]*transition-property:\s*transform/);
    expect(css).not.toContain('--spin-ms');
  });

  it('reduced-motion block no longer overrides a disc transition', () => {
    const cssPath = path.resolve(process.cwd(), 'src/components/wheel/wheel.css');
    const css = readFileSync(cssPath, 'utf8');
    const reducedBlock = css.slice(css.indexOf('@media (prefers-reduced-motion: reduce)'));
    // Gentle mode is handled in JS (useWheelPhysics), not by a CSS transition
    // override. The old `.wheel-disc.is-spinning { transition-duration: ... }`
    // escape hatch must be gone; only the decorative bulb chase is disabled.
    expect(reducedBlock).not.toContain('.wheel-disc.is-spinning');
    expect(reducedBlock).toContain('.wheel-bulb');
  });

  it('uses a smaller label font for more segments', () => {
    const { container: few } = render(
      <Wheel segments={makeSegments(6)} spinning={false} spinLabel="S" disabled={false} onSpin={() => {}} />,
    );
    const fewSize = few.querySelector('text')?.getAttribute('font-size');
    cleanup();
    const { container: many } = render(
      <Wheel segments={makeSegments(30)} spinning={false} spinLabel="S" disabled={false} onSpin={() => {}} />,
    );
    const manySize = many.querySelector('text')?.getAttribute('font-size');
    expect(Number(fewSize)).toBeGreaterThan(Number(manySize));
  });
});
