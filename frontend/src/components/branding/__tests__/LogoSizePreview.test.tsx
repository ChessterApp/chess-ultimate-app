// @vitest-environment jsdom
import { describe, it, expect, afterEach } from 'vitest';
import { render, screen, cleanup } from '@testing-library/react';
import React from 'react';

import { LogoSizePreview } from '../LogoSizePreview';

afterEach(cleanup);

describe('LogoSizePreview', () => {
  it('renders nothing when there is neither a logo nor a mark', () => {
    const { container } = render(<LogoSizePreview />);
    expect(container.firstChild).toBeNull();
  });

  it('renders the logo at 24/32/40px on both light and dark swatches', () => {
    render(<LogoSizePreview logoUrl="https://x/logo.png" />);
    // 3 sizes × 2 swatches (light + dark) = 6 images.
    const imgs = screen.getAllByRole('img') as HTMLImageElement[];
    expect(imgs).toHaveLength(6);
    const sizes = new Set(imgs.map(i => i.getAttribute('data-size')));
    expect([...sizes].sort()).toEqual(['24', '32', '40']);
    expect(imgs.every(i => i.src.includes('logo.png'))).toBe(true);
  });

  it('renders both the logo and the mark rows when both are provided', () => {
    render(
      <LogoSizePreview logoUrl="https://x/logo.png" markUrl="https://x/mark.png" />,
    );
    const imgs = screen.getAllByRole('img') as HTMLImageElement[];
    // 2 rows × 3 sizes × 2 swatches = 12 images.
    expect(imgs).toHaveLength(12);
    expect(imgs.some(i => i.src.includes('mark.png'))).toBe(true);
    expect(imgs.some(i => i.src.includes('logo.png'))).toBe(true);
  });
});
