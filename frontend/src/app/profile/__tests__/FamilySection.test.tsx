/**
 * @vitest-environment jsdom
 *
 * FamilySection — the Family card on the profile page. Lists verified Chess
 * Empire members, gates removal to child/other rows, runs the confirm → DELETE
 * flow, and self-hides when the account has no verified links.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import React from 'react';
import { render, screen, cleanup, fireEvent, waitFor } from '@testing-library/react';
import { NextIntlClientProvider } from 'next-intl';

import en from '../../../../messages/en.json';
import FamilySection from '../FamilySection';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ refresh: vi.fn(), push: vi.fn(), replace: vi.fn() }),
}));

const fetchMock = vi.fn();

function renderSection() {
  return render(
    <NextIntlClientProvider locale="en" messages={en as Record<string, unknown>}>
      <FamilySection />
    </NextIntlClientProvider>,
  );
}

function membersResponse(members: unknown[]) {
  return { ok: true, json: async () => ({ members, branchToken: null }) };
}

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal('fetch', fetchMock);
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe('FamilySection', () => {
  it('renders nothing when the account has no verified links', async () => {
    fetchMock.mockResolvedValue(membersResponse([]));
    const { container } = renderSection();
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    // Card self-hides — no title rendered.
    expect(screen.queryByText(en.family.title)).toBeNull();
    expect(container.querySelector('h2')).toBeNull();
  });

  it('lists members with relationship tags; only child/other rows are removable', async () => {
    fetchMock.mockResolvedValue(
      membersResponse([
        { studentId: 'stu-self', name: 'Alex Parent', relationship: 'self', status: 'verified' },
        { studentId: 'stu-kid', name: 'Aruzhan Kid', relationship: 'child', status: 'verified' },
      ]),
    );
    renderSection();

    expect(await screen.findByText('Alex Parent')).toBeTruthy();
    expect(screen.getByText('Aruzhan Kid')).toBeTruthy();
    // Relationship tags (ceTournaments.relationship.*).
    expect(screen.getByText(en.ceTournaments.relationship.self)).toBeTruthy();
    expect(screen.getByText(en.ceTournaments.relationship.child)).toBeTruthy();
    // Exactly one remove control (the child); the self row has none.
    const removeButtons = screen.getAllByRole('button', {
      name: new RegExp(en.family.removeMember),
    });
    expect(removeButtons).toHaveLength(1);
  });

  it('single self-only member still shows the card with the add affordance', async () => {
    fetchMock.mockResolvedValue(
      membersResponse([
        { studentId: 'stu-self', name: 'Solo', relationship: 'self', status: 'verified' },
      ]),
    );
    renderSection();

    expect(
      await screen.findByRole('heading', { name: new RegExp(en.family.title) }),
    ).toBeTruthy();
    expect(
      screen.getByRole('button', { name: new RegExp(en.ceTournaments.addFamilyMember) }),
    ).toBeTruthy();
    // No removable rows.
    expect(
      screen.queryByRole('button', { name: new RegExp(en.family.removeMember) }),
    ).toBeNull();
  });

  it('confirms and removes a child via DELETE', async () => {
    fetchMock.mockImplementation((url: string, opts?: RequestInit) => {
      if (url.includes('/link/members/')) {
        expect(opts?.method).toBe('DELETE');
        return Promise.resolve({ ok: true, json: async () => ({ ok: true }) });
      }
      return Promise.resolve(
        membersResponse([
          { studentId: 'stu-kid', name: 'Aruzhan Kid', relationship: 'child', status: 'verified' },
        ]),
      );
    });
    renderSection();

    const removeBtn = await screen.findByRole('button', {
      name: new RegExp(en.family.removeMember),
    });
    fireEvent.click(removeBtn);

    // Confirm copy — including the "NOT cancelled" reassurance.
    expect(screen.getByText(en.family.removeConfirmBody)).toBeTruthy();
    fireEvent.click(
      screen.getByRole('button', { name: en.family.removeConfirmButton }),
    );

    await waitFor(() => {
      expect(
        fetchMock.mock.calls.some(
          (c) => String(c[0]).includes('/link/members/stu-kid') && c[1]?.method === 'DELETE',
        ),
      ).toBe(true);
    });
    // Row disappears after a successful unlink.
    await waitFor(() => expect(screen.queryByText('Aruzhan Kid')).toBeNull());
  });

  it('shows an error and keeps the row when the delete fails', async () => {
    fetchMock.mockImplementation((url: string) => {
      if (url.includes('/link/members/')) {
        return Promise.resolve({ ok: false, json: async () => ({ error: 'server_error' }) });
      }
      return Promise.resolve(
        membersResponse([
          { studentId: 'stu-kid', name: 'Aruzhan Kid', relationship: 'child', status: 'verified' },
        ]),
      );
    });
    renderSection();

    fireEvent.click(
      await screen.findByRole('button', { name: new RegExp(en.family.removeMember) }),
    );
    fireEvent.click(
      screen.getByRole('button', { name: en.family.removeConfirmButton }),
    );

    expect(await screen.findByText(en.family.removeError)).toBeTruthy();
    expect(screen.getByText('Aruzhan Kid')).toBeTruthy();
  });
});
