import { describe, it, expect } from 'vitest';
import { buildMyGameShareUrl } from '@/components/openings/ShareMyGameButton';

describe('buildMyGameShareUrl', () => {
  it('builds a /g/u/<token> short link for an owned game', () => {
    expect(buildMyGameShareUrl('https://chesster.io', 'abc123')).toBe(
      'https://chesster.io/g/u/abc123',
    );
  });

  it('carries only the opaque token — never a game id or user id', () => {
    const url = buildMyGameShareUrl('https://chesster.io', 'Xy_z-9');
    expect(url).toBe('https://chesster.io/g/u/Xy_z-9');
  });
});
