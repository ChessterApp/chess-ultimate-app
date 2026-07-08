import { describe, it, expect } from 'vitest';
import { existsSync, readFileSync } from 'fs';
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

describe('Coach Page - Premium Gating', () => {
  const pageContent = readFileSync(resolve(__dirname, '../page.tsx'), 'utf-8');

  it('imports UpgradePrompt component', () => {
    expect(pageContent).toContain("import UpgradePrompt from '@/components/UpgradePrompt'");
  });

  it('renders UpgradePrompt for non-premium users', () => {
    expect(pageContent).toContain("<UpgradePrompt feature={t('feature')}");
  });

  it('checks subscription.active before rendering coach UI', () => {
    expect(pageContent).toContain('!subscription.active');
  });

  it('does not redirect non-premium users to dashboard', () => {
    // Should show UpgradePrompt instead of redirecting
    expect(pageContent).not.toContain("router.push('/dashboard')");
  });

  it('still redirects unauthenticated users to sign-in', () => {
    expect(pageContent).toContain("router.push('/sign-in')");
  });
});
