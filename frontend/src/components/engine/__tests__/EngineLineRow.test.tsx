/**
 * @vitest-environment jsdom
 */
import { describe, it, expect, afterEach, vi } from 'vitest';
import { render, screen, fireEvent, cleanup } from '@testing-library/react';
import EngineLineRow, { EngineLineRowSkeleton, formatEval } from '../EngineLineRow';
import { formatEngineLine } from '@/lib/engine/formatEngineLine';

const START = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1';

describe('EngineLineRow', () => {
  afterEach(cleanup);

  it('renders numbered moves', () => {
    render(<EngineLineRow cp={42} tokens={formatEngineLine(START, ['e2e4', 'e7e5', 'g1f3'])} />);
    expect(screen.getByTestId('engine-line-moves').textContent).toBe('1.e4 e5 2.Nf3');
    expect(screen.getByText('1.')).toBeTruthy();
    expect(screen.getByText('+0.42')).toBeTruthy();
  });

  it('keeps the moves on a single non-wrapping row', () => {
    render(<EngineLineRow cp={0} tokens={formatEngineLine(START, ['e2e4'])} />);
    const style = window.getComputedStyle(screen.getByTestId('engine-line-moves'));
    expect(style.whiteSpace).toBe('nowrap');
    expect(style.overflow).toBe('hidden');
  });

  it('formats evaluations including mate', () => {
    expect(formatEval(42)).toBe('+0.42');
    expect(formatEval(-110)).toBe('-1.10');
    expect(formatEval(0)).toBe('+0.00');
    expect(formatEval(undefined, 3)).toBe('M3');
    expect(formatEval(500, -2)).toBe('-M2');
    render(<EngineLineRow mate={3} tokens={[]} winPercent={99.6} />);
    expect(screen.getByText('M3')).toBeTruthy();
    expect(screen.getByText('100%')).toBeTruthy();
  });

  it('calls onClick and renders a skeleton placeholder', () => {
    const onClick = vi.fn();
    render(
      <>
        <EngineLineRow cp={10} tokens={[]} onClick={onClick} />
        <EngineLineRowSkeleton />
      </>,
    );
    fireEvent.click(screen.getByRole('button'));
    expect(onClick).toHaveBeenCalledTimes(1);
    expect(screen.getByTestId('engine-line-skeleton')).toBeTruthy();
  });
});
