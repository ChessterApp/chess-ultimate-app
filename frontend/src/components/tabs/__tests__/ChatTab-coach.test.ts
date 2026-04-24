import { describe, it, expect } from 'vitest';
import { readFileSync } from 'fs';
import { resolve } from 'path';

describe('ChatTab - CoachToggle Integration', () => {
  const chatTabContent = readFileSync(
    resolve(__dirname, '../ChatTab.tsx'),
    'utf-8'
  );

  it('imports CoachToggle component', () => {
    expect(chatTabContent).toContain('import CoachToggle from');
  });

  it('ChatTabProps includes isCoachMode', () => {
    expect(chatTabContent).toContain('isCoachMode');
  });

  it('ChatTabProps includes onCoachModeToggle', () => {
    expect(chatTabContent).toContain('onCoachModeToggle');
  });

  it('renders CoachToggle in toolbar', () => {
    expect(chatTabContent).toContain('<CoachToggle');
  });

  it('passes isCoachMode to CoachToggle', () => {
    expect(chatTabContent).toMatch(/isCoachMode=\{isCoachMode\}/);
  });

  it('passes onToggle callback to CoachToggle', () => {
    expect(chatTabContent).toMatch(/onToggle=\{onCoachModeToggle/);
  });

  it('isCoachMode defaults to false', () => {
    expect(chatTabContent).toContain('isCoachMode = false');
  });
});

describe('ChessterAnalysisView - Coach Mode State', () => {
  const viewContent = readFileSync(
    resolve(__dirname, '../../analysis/ChessterAnalysisView.tsx'),
    'utf-8'
  );

  it('manages isCoachMode state', () => {
    expect(viewContent).toContain('isCoachMode');
    expect(viewContent).toContain('setIsCoachMode');
  });

  it('passes isCoachMode to ChatTab', () => {
    expect(viewContent).toContain('isCoachMode={isCoachMode}');
  });

  it('passes onCoachModeToggle to ChatTab', () => {
    expect(viewContent).toContain('onCoachModeToggle={handleCoachModeToggle}');
  });
});
