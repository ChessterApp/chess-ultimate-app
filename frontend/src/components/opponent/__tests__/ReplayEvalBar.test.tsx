/**
 * @vitest-environment jsdom
 */
import { describe, it, expect, afterEach } from 'vitest';
import React from 'react';
import { cleanup, render } from '@testing-library/react';
import ReplayEvalBar from '../ReplayEvalBar';

afterEach(cleanup);

describe('ReplayEvalBar width', () => {
  it('defaults to 32px wide', () => {
    const { container } = render(<ReplayEvalBar evaluation={null} isAnalyzing={false} depth={0} height={300} />);
    const bar = container.firstChild as HTMLElement;
    expect(bar.style.width).toBe('32px');
    expect(bar.style.height).toBe('300px');
  });

  it('honours a custom width', () => {
    const { container } = render(<ReplayEvalBar evaluation={{ cp: 50 }} isAnalyzing={false} depth={12} width={16} />);
    expect((container.firstChild as HTMLElement).style.width).toBe('16px');
  });
});
