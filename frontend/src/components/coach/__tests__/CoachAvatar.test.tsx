/**
 * @vitest-environment jsdom
 */
import React from 'react';
import { describe, it, expect, afterEach } from 'vitest';
import { render, cleanup } from '@testing-library/react';

import CoachAvatar from '../CoachAvatar';

describe('CoachAvatar', () => {
  afterEach(cleanup);

  it('shows the Chesster zebra, never another mascot', () => {
    const { container } = render(<CoachAvatar size={40} />);
    const img = container.querySelector('img');
    expect(img).not.toBeNull();
    const src = decodeURIComponent(img!.getAttribute('src') ?? '');
    expect(src).toContain('chesster-logo-v3.png');
    expect(src).not.toMatch(/fox/i);
  });
});
