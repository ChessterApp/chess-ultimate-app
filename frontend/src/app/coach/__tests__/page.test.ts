import { describe, it, expect } from 'vitest';
import { existsSync } from 'fs';
import { resolve } from 'path';

describe('CoachPage - File Structure', () => {
  const coachDir = resolve(__dirname, '..');

  it('page.tsx exists', () => {
    expect(existsSync(resolve(coachDir, 'page.tsx'))).toBe(true);
  });

  it('layout.tsx exists', () => {
    expect(existsSync(resolve(coachDir, 'layout.tsx'))).toBe(true);
  });

  it('layout exports a default function', async () => {
    const CoachLayout = (await import('../layout')).default;
    expect(typeof CoachLayout).toBe('function');
  });
});

describe('Coach Components - File Structure', () => {
  const componentsDir = resolve(__dirname, '../../../components/coach');

  it('CoachBoard.tsx exists', () => {
    expect(existsSync(resolve(componentsDir, 'CoachBoard.tsx'))).toBe(true);
  });

  it('CoachChat.tsx exists', () => {
    expect(existsSync(resolve(componentsDir, 'CoachChat.tsx'))).toBe(true);
  });

  it('BoardControls.tsx exists', () => {
    expect(existsSync(resolve(componentsDir, 'BoardControls.tsx'))).toBe(true);
  });

  it('PuzzleOverlay.tsx exists', () => {
    expect(existsSync(resolve(componentsDir, 'PuzzleOverlay.tsx'))).toBe(true);
  });

  it('ToolIndicator.tsx exists', () => {
    expect(existsSync(resolve(componentsDir, 'ToolIndicator.tsx'))).toBe(true);
  });

  it('CoachToggle.tsx exists', () => {
    expect(existsSync(resolve(componentsDir, 'CoachToggle.tsx'))).toBe(true);
  });
});
