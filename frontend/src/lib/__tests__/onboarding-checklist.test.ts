import { describe, it, expect } from 'vitest';
import {
  computeChecklist,
  completionPercentage,
  isAllCompleted,
  shouldShowChecklist,
} from '../onboarding-checklist';

function snap(over: Partial<Parameters<typeof computeChecklist>[0]['org']> = {},
              counts: { students?: number; teachers?: number } = {}) {
  return {
    org: {
      logoUrl: null,
      primaryColor: '#1a73e8',
      secondaryColor: '#ffffff',
      accentColor: '#ffd700',
      customDomainStatus: null,
      emailSenderStatus: null,
      landingPageConfig: null,
      createdAt: '2026-06-01T00:00:00Z',
      plan: 'starter',
      ...over,
    },
    studentCount: counts.students ?? 0,
    teacherCount: counts.teachers ?? 0,
  };
}

describe('computeChecklist', () => {
  it('marks upload_logo complete when logoUrl present', () => {
    const items = computeChecklist(snap({ logoUrl: 'https://x/y.png' }));
    expect(items.find(i => i.id === 'upload_logo')?.completed).toBe(true);
  });

  it('marks pick_colors complete when primaryColor differs from default', () => {
    const items = computeChecklist(snap({ primaryColor: '#7b1fa2' }));
    expect(items.find(i => i.id === 'pick_colors')?.completed).toBe(true);
  });

  it('hides pro-only items on starter plan', () => {
    const items = computeChecklist(snap({ plan: 'starter' }));
    expect(items.find(i => i.id === 'verify_sender')?.hidden).toBe(true);
    expect(items.find(i => i.id === 'connect_domain')?.hidden).toBe(true);
  });

  it('shows pro-only items on pro plan', () => {
    const items = computeChecklist(snap({ plan: 'pro' }));
    expect(items.find(i => i.id === 'verify_sender')?.hidden).toBeFalsy();
    expect(items.find(i => i.id === 'connect_domain')?.hidden).toBeFalsy();
  });

  it('requires 5+ students for invite_students', () => {
    expect(
      computeChecklist(snap({}, { students: 4 })).find(i => i.id === 'invite_students')?.completed,
    ).toBe(false);
    expect(
      computeChecklist(snap({}, { students: 5 })).find(i => i.id === 'invite_students')?.completed,
    ).toBe(true);
  });

  it('detects landing page configured when config has any entries', () => {
    const items = computeChecklist(snap({ landingPageConfig: { hero_title: 'x' } }));
    expect(items.find(i => i.id === 'publish_landing')?.completed).toBe(true);
  });
});

describe('completionPercentage', () => {
  it('returns 0 when nothing complete', () => {
    expect(completionPercentage(computeChecklist(snap()))).toBe(0);
  });

  it('reaches 100 when all visible items complete on starter', () => {
    const items = computeChecklist(snap(
      {
        logoUrl: 'https://x',
        primaryColor: '#7b1fa2',
        landingPageConfig: { hero_title: 'X' },
      },
      { students: 5, teachers: 1 },
    ));
    expect(completionPercentage(items)).toBe(100);
    expect(isAllCompleted(items)).toBe(true);
  });

  it('ignores hidden items in the percentage math', () => {
    const items = computeChecklist(snap(
      {
        logoUrl: 'https://x',
        primaryColor: '#7b1fa2',
        landingPageConfig: { hero_title: 'X' },
        plan: 'starter',
      },
      { students: 5, teachers: 1 },
    ));
    expect(completionPercentage(items)).toBe(100);
  });

  it('partial completion is rounded', () => {
    const items = computeChecklist(snap(
      { logoUrl: 'https://x', plan: 'starter' },
      { students: 5 },
    ));
    // 2 / 5 visible = 40%
    expect(completionPercentage(items)).toBe(40);
  });
});

describe('shouldShowChecklist', () => {
  it('hides once 100% complete', () => {
    const s = snap(
      { logoUrl: 'https://x', primaryColor: '#aaaaaa', landingPageConfig: { x: 1 } },
      { students: 5, teachers: 1 },
    );
    expect(shouldShowChecklist(s)).toBe(false);
  });

  it('hides after 7 days', () => {
    const s = snap({ createdAt: '2026-05-01T00:00:00Z' });
    const now = new Date('2026-06-01T00:00:00Z');
    expect(shouldShowChecklist(s, now)).toBe(false);
  });

  it('shows within 7 days when incomplete', () => {
    const s = snap({ createdAt: '2026-05-30T00:00:00Z' });
    const now = new Date('2026-06-01T00:00:00Z');
    expect(shouldShowChecklist(s, now)).toBe(true);
  });
});
