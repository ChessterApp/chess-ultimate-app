/**
 * @vitest-environment jsdom
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import TournamentRegisterPage from '../page';

// Stable Clerk mock — must not produce a new object/function per render.
const stableGetToken = vi.fn().mockResolvedValue('test-token');
vi.mock('@clerk/nextjs', () => ({
  useAuth: () => ({ getToken: stableGetToken }),
}));

vi.mock('next/link', () => ({
  default: ({ children, href }: { children: React.ReactNode; href: string }) => (
    <a href={href}>{children}</a>
  ),
}));

const push = vi.fn();
vi.mock('next/navigation', () => ({
  useParams: () => ({ id: 'tour-1' }),
  useRouter: () => ({ push }),
}));

function mockEligibility(body: Record<string, unknown>) {
  global.fetch = vi.fn((url: string) => {
    if (typeof url === 'string' && url.includes('/eligibility')) {
      return Promise.resolve({ ok: true, json: () => Promise.resolve(body) });
    }
    return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
  }) as unknown as typeof fetch;
}

describe('Tournament registration — League C level gate', () => {
  beforeEach(() => {
    push.mockReset();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('shows the banner and disables submit for a Level 1 student on League C', async () => {
    mockEligibility({
      league: 'C',
      eligible: false,
      code: 'level_too_low',
      message: "League C tournaments require Level 2+. You're on Level 1 — complete your Level 1 lessons to unlock registration.",
    });

    render(<TournamentRegisterPage />);

    const banner = await screen.findByRole('alert');
    expect(banner.textContent).toMatch(/Level 2\+/);

    const submit = screen.getByRole('button', { name: /register/i });
    expect((submit as HTMLButtonElement).disabled).toBe(true);
  });

  it('shows no banner and keeps submit enabled for a Level 2+ student on League C', async () => {
    mockEligibility({ league: 'C', eligible: true });

    render(<TournamentRegisterPage />);

    // Let the eligibility effect resolve, then assert no banner appeared.
    await waitFor(() => expect(global.fetch).toHaveBeenCalled());
    expect(screen.queryByRole('alert')).toBeNull();

    // With a name entered, submit is enabled — the gate does not block Level 2+.
    const nameInput = screen.getByPlaceholderText(/your full name/i) as HTMLInputElement;
    fireEvent.change(nameInput, { target: { value: 'Level Two Player' } });
    const submit = screen.getByRole('button', { name: /register/i }) as HTMLButtonElement;
    expect(submit.disabled).toBe(false);
  });

  it('shows no banner for a non-League-C tournament', async () => {
    mockEligibility({ league: null, eligible: true });

    render(<TournamentRegisterPage />);

    await waitFor(() => expect(global.fetch).toHaveBeenCalled());
    expect(screen.queryByRole('alert')).toBeNull();
  });
});
