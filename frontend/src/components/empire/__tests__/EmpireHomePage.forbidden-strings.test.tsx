/**
 * @vitest-environment jsdom
 *
 * Guards against name-fallback regressions on the verified EmpireHomePage.
 *
 * The Chess Empire personalized homepage plan bans any greeted name from
 * the following sources:
 *  - Clerk `user.firstName`
 *  - the email prefix (`dagamavasco…` from `dagamavasco210@gmail.com`)
 *  - hardcoded design-mockup placeholders (`Vasco`, `Turabay`)
 *
 * This test renders the verified state with the Vasco fixture from the
 * V1 mockup and asserts that none of those strings leak into the HTML.
 */
import { describe, it, expect, vi } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';

vi.mock('next-intl/server', () => ({
  getTranslations: async () => (key: string, values?: Record<string, unknown>) => {
    if (!values) return key;
    const parts = Object.entries(values)
      .map(([k, v]) => `${k}=${String(v)}`)
      .join(',');
    return `${key}[${parts}]`;
  },
}));

vi.mock('../PendingConfirmBanner', () => ({
  __esModule: true,
  default: () => null,
}));

import EmpireHomePage from '../EmpireHomePage';
import type { CEStudentProfile } from '@/lib/chess-empire-client';

const forbidden = ['Vasco', 'dagamavasco', 'Turabay', 'user.firstName'];

describe('EmpireHomePage — forbidden fallback strings', () => {
  it('renders no forbidden identity fallback in verified state', async () => {
    const profile: CEStudentProfile = {
      id: 'stu-vasco',
      first_name: 'Ali',
      last_name: 'M.',
      branch_id: 'br-1',
      status: 'active',
      date_of_birth: null,
      branch_name: 'Gagarin Park',
      coach_name: 'Vasily Mikhaylovich',
      razryad: '3rd',
      current_rating: 856,
      current_level: 7,
      current_lesson: 94,
      total_lessons: 120,
    };
    const ui = await EmpireHomePage({
      state: 'verified',
      studentDisplayName: 'Ali',
      profile,
      ratings: [
        { date: '2026-05-01', rating: 800 },
        { date: '2026-06-01', rating: 856 },
      ],
      achievements: [
        { id: 'a1', name: 'Bot Slayer', earned_at: '2026-05-01' },
      ],
      rank: { branch_rank: null, school_rank: 1, branch_size: null, school_size: 85 },
    });
    const html = renderToStaticMarkup(ui);
    for (const s of forbidden) {
      expect(html, `forbidden string "${s}" leaked into HTML`).not.toContain(s);
    }
    // Sanity: the greeting IS present with the resolved name.
    expect(html).toContain('welcomeBackNamed');
    expect(html).toContain('name=Ali');
  });

  it('renders no forbidden identity fallback in name-less verified state', async () => {
    const profile: CEStudentProfile = {
      id: 'stu-x',
      first_name: '',
      last_name: '',
      branch_id: 'br-1',
      status: 'active',
      date_of_birth: null,
    };
    const ui = await EmpireHomePage({
      state: 'verified',
      studentDisplayName: null,
      profile,
      ratings: [],
      achievements: [],
      rank: {
        branch_rank: null,
        school_rank: null,
        branch_size: null,
        school_size: null,
      },
    });
    const html = renderToStaticMarkup(ui);
    for (const s of forbidden) {
      expect(html).not.toContain(s);
    }
    expect(html).toContain('welcomeBack');
    expect(html).not.toContain('welcomeBackNamed');
  });
});
