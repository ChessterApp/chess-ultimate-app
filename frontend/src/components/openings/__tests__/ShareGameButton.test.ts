import { describe, it, expect, vi } from 'vitest';
import { buildGameShareUrl, shareOrCopyGame } from '@/components/openings/ShareGameButton';
import { decodeGameSlug } from '@/lib/gameSlug';

describe('buildGameShareUrl', () => {
  it('builds an opaque /database?g= link that decodes back to the game', () => {
    const url = buildGameShareUrl('https://chesster.io', 'twic', 12345);
    expect(url.startsWith('https://chesster.io/database?g=')).toBe(true);
    const slug = new URL(url).searchParams.get('g')!;
    expect(decodeGameSlug(slug)).toEqual({ source: 'twic', id: 12345 });
  });

  it('never leaks the source name into the link', () => {
    const lower = buildGameShareUrl('https://chesster.io', 'lichess', 987654).toLowerCase();
    expect(lower).not.toContain('lichess');
    expect(lower).not.toContain('twic');
  });
});

describe('shareOrCopyGame', () => {
  it('uses the native share sheet when navigator.share exists', async () => {
    const share = vi.fn().mockResolvedValue(undefined);
    const writeText = vi.fn().mockResolvedValue(undefined);
    const nav = { share, clipboard: { writeText } } as unknown as Navigator;

    const method = await shareOrCopyGame({ url: 'https://x/g', title: 'A vs B · Chesster', nav });

    expect(method).toBe('share');
    expect(share).toHaveBeenCalledWith({ title: 'A vs B · Chesster', url: 'https://x/g' });
    expect(writeText).not.toHaveBeenCalled();
  });

  it('falls back to clipboard when navigator.share is unavailable', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    const nav = { clipboard: { writeText } } as unknown as Navigator;

    const method = await shareOrCopyGame({ url: 'https://x/g', title: 'A vs B · Chesster', nav });

    expect(method).toBe('clipboard');
    expect(writeText).toHaveBeenCalledWith('https://x/g');
  });

  it('propagates a rejected native share (e.g. user cancel)', async () => {
    const err = Object.assign(new Error('cancelled'), { name: 'AbortError' });
    const share = vi.fn().mockRejectedValue(err);
    const nav = { share } as unknown as Navigator;

    await expect(
      shareOrCopyGame({ url: 'https://x/g', title: 't', nav })
    ).rejects.toThrow('cancelled');
  });
});
