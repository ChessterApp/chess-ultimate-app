/**
 * @vitest-environment jsdom
 *
 * Server-component tests for StudentCard. Mocks next-intl/server and awaits
 * the async component before handing the JSX to React Testing Library.
 */
import { describe, it, expect, afterEach, vi } from 'vitest';
import React from 'react';
import { cleanup, render } from '@testing-library/react';

vi.mock('next-intl/server', () => ({
  getTranslations: async () => (key: string) => key,
}));

import StudentCard from '../StudentCard';
import type { CEStudentProfile } from '@/lib/chess-empire-client';

afterEach(() => {
  cleanup();
});

const baseProfile: CEStudentProfile = {
  id: 'stu-1',
  first_name: 'Aiman',
  last_name: 'Karim',
  branch_id: 'br-1',
  status: 'active',
  date_of_birth: '2015-04-12',
  branch_name: 'Debut',
  coach_name: 'Anna',
  razryad: 'III',
  current_league: 'Bronze',
  current_lesson: 12,
  total_lessons: 24,
  current_level: 3,
  current_rating: 1200,
  photo_url: null,
};

describe('StudentCard', () => {
  it('renders full name, branch, coach, razryad, league', async () => {
    const ui = await StudentCard({ profile: baseProfile });
    const { getByTestId } = render(ui);
    const card = getByTestId('empire-student-card');
    expect(card.textContent).toContain('Aiman Karim');
    expect(card.textContent).toContain('Debut');
    expect(card.textContent).toContain('Anna');
    expect(card.textContent).toContain('III');
    expect(card.textContent).toContain('Bronze');
  });

  it('renders photo with src when photo_url is present', async () => {
    const ui = await StudentCard({
      profile: { ...baseProfile, photo_url: 'https://cdn/photo.jpg' },
    });
    const { getByTestId, queryByTestId } = render(ui);
    const photo = getByTestId('empire-student-photo') as HTMLImageElement;
    expect(photo.src).toContain('https://cdn/photo.jpg');
    expect(queryByTestId('empire-student-initials')).toBeNull();
  });

  it('falls back to initials when photo_url is null', async () => {
    const ui = await StudentCard({ profile: baseProfile });
    const { getByTestId, queryByTestId } = render(ui);
    const initials = getByTestId('empire-student-initials');
    expect(initials.textContent).toBe('AK');
    expect(queryByTestId('empire-student-photo')).toBeNull();
  });

  it('shows em-dash when fields are missing', async () => {
    const ui = await StudentCard({
      profile: {
        ...baseProfile,
        first_name: '',
        last_name: '',
        branch_name: null,
        coach_name: null,
        razryad: null,
        current_league: null,
      },
    });
    const { getByTestId } = render(ui);
    const card = getByTestId('empire-student-card');
    expect(card.textContent).toContain('—');
  });
});
