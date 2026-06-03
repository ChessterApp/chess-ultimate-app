import { describe, it, expect } from 'vitest';
import { buildLoomConfig, loomEmbedUrl, pickLoomForTier } from '../loom';

describe('loomEmbedUrl', () => {
  it('normalises share URL to embed URL', () => {
    expect(loomEmbedUrl('https://www.loom.com/share/abc123def456'))
      .toBe('https://www.loom.com/embed/abc123def456');
  });

  it('normalises non-www share URL', () => {
    expect(loomEmbedUrl('https://loom.com/share/xyz789'))
      .toBe('https://www.loom.com/embed/xyz789');
  });

  it('keeps embed URL as-is (normalised)', () => {
    expect(loomEmbedUrl('https://www.loom.com/embed/abc123def456'))
      .toBe('https://www.loom.com/embed/abc123def456');
  });

  it('strips query strings/fragments from share URL', () => {
    expect(loomEmbedUrl('https://www.loom.com/share/abc123def?t=10'))
      .toBe('https://www.loom.com/embed/abc123def');
  });

  it('accepts a bare video id (8+ chars)', () => {
    expect(loomEmbedUrl('abc12345def')).toBe(
      'https://www.loom.com/embed/abc12345def',
    );
  });

  it('returns null for non-loom URLs', () => {
    expect(loomEmbedUrl('https://youtube.com/watch?v=foo')).toBeNull();
  });

  it('returns null for empty / null / undefined / garbage', () => {
    expect(loomEmbedUrl(null)).toBeNull();
    expect(loomEmbedUrl(undefined)).toBeNull();
    expect(loomEmbedUrl('')).toBeNull();
    expect(loomEmbedUrl('   ')).toBeNull();
    expect(loomEmbedUrl('javascript:alert(1)')).toBeNull();
  });

  it('returns null for too-short bare ids', () => {
    expect(loomEmbedUrl('abc12')).toBeNull();
  });
});

describe('buildLoomConfig', () => {
  it('emits null welcome when env var missing', () => {
    const cfg = buildLoomConfig({});
    expect(cfg.welcomeUrl).toBeNull();
    expect(cfg.tierUrls).toEqual({});
  });

  it('populates welcome + tier maps', () => {
    const cfg = buildLoomConfig({
      NEXT_PUBLIC_LOOM_WELCOME_URL: 'https://www.loom.com/share/wel1234567',
      NEXT_PUBLIC_LOOM_GROWTH_URL: 'https://www.loom.com/share/gro1234567',
      NEXT_PUBLIC_LOOM_PRO_URL: 'https://www.loom.com/share/pro1234567',
    });
    expect(cfg.welcomeUrl).toBe('https://www.loom.com/embed/wel1234567');
    expect(cfg.tierUrls.growth).toBe('https://www.loom.com/embed/gro1234567');
    expect(cfg.tierUrls.pro).toBe('https://www.loom.com/embed/pro1234567');
    expect(cfg.tierUrls.starter).toBeUndefined();
  });
});

describe('pickLoomForTier', () => {
  const cfg = buildLoomConfig({
    NEXT_PUBLIC_LOOM_WELCOME_URL: 'https://www.loom.com/share/wel1234567',
    NEXT_PUBLIC_LOOM_GROWTH_URL: 'https://www.loom.com/share/gro1234567',
  });

  it('picks tier-specific URL when available', () => {
    expect(pickLoomForTier(cfg, 'growth')).toBe(
      'https://www.loom.com/embed/gro1234567',
    );
  });

  it('falls back to welcome URL', () => {
    expect(pickLoomForTier(cfg, 'starter')).toBe(
      'https://www.loom.com/embed/wel1234567',
    );
    expect(pickLoomForTier(cfg, 'pro')).toBe(
      'https://www.loom.com/embed/wel1234567',
    );
  });

  it('returns welcome for null tier', () => {
    expect(pickLoomForTier(cfg, null)).toBe(
      'https://www.loom.com/embed/wel1234567',
    );
  });
});
