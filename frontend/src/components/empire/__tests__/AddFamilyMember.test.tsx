/**
 * @vitest-environment jsdom
 *
 * AddFamilyMember — the in-app "add another child" flow on the tournaments
 * page. Reuses the public search → verify → claim endpoints but writes
 * `relationship='child'`. The branch token is recovered from the durable
 * branch-welcome URL the parent's own onboarding stashed.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import React from 'react';
import {
  render,
  screen,
  cleanup,
  fireEvent,
  waitFor,
} from '@testing-library/react';
import { NextIntlClientProvider } from 'next-intl';

import en from '../../../../messages/en.json';
import { CE_BRANCH_WELCOME_URL_STORAGE_KEY } from '@/lib/invite-storage';
import AddFamilyMember from '../AddFamilyMember';

const refreshMock = vi.fn();
vi.mock('next/navigation', () => ({
  useRouter: () => ({ refresh: refreshMock, push: vi.fn(), replace: vi.fn() }),
}));

const fetchMock = vi.fn();

function renderAdd() {
  return render(
    <NextIntlClientProvider locale="en" messages={en as Record<string, unknown>}>
      <AddFamilyMember />
    </NextIntlClientProvider>,
  );
}

beforeEach(() => {
  fetchMock.mockReset();
  refreshMock.mockReset();
  vi.stubGlobal('fetch', fetchMock);
  localStorage.setItem(CE_BRANCH_WELCOME_URL_STORAGE_KEY, '/welcome/tok-1');
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  localStorage.clear();
});

describe('AddFamilyMember', () => {
  it('searches, confirms and links a child with relationship=child', async () => {
    fetchMock.mockImplementation((url: string, opts?: RequestInit) => {
      if (url.includes('/students/search')) {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            results: [
              {
                studentId: 'stu-new',
                firstName: 'Aruzhan',
                lastName: 'A',
                branchName: 'Debut',
                type: 'student',
              },
            ],
          }),
        });
      }
      if (url.includes('/students/verify')) {
        expect(opts?.method).toBe('POST');
        expect(JSON.parse(String(opts?.body))).toEqual({
          branchToken: 'tok-1',
          studentId: 'stu-new',
          relationship: 'child',
        });
        return Promise.resolve({
          ok: true,
          json: async () => ({ inviteJwt: 'jwt-xyz' }),
        });
      }
      if (url.includes('/link/claim')) {
        return Promise.resolve({ ok: true, json: async () => ({ ok: true }) });
      }
      return Promise.resolve({ ok: false, json: async () => ({}) });
    });

    renderAdd();
    fireEvent.click(
      screen.getByRole('button', {
        name: new RegExp(en.ceTournaments.addFamilyMember),
      }),
    );

    const input = await screen.findByLabelText(
      en.ceTournaments.addMemberSearchPlaceholder,
    );
    fireEvent.change(input, { target: { value: 'aru' } });

    const result = await screen.findByRole('button', { name: /Aruzhan/ });
    fireEvent.click(result);

    // Confirm step (relationship defaults to 'child'); submit.
    fireEvent.click(
      screen.getByRole('button', { name: en.ceTournaments.addMemberSubmit }),
    );

    await waitFor(() => {
      expect(
        fetchMock.mock.calls.some((c) => String(c[0]).includes('/link/claim')),
      ).toBe(true);
    });
    expect(refreshMock).toHaveBeenCalled();
  });

  it('falls back to server-side branch resolution when device storage is empty', async () => {
    localStorage.clear();
    fetchMock.mockImplementation((url: string) => {
      if (url.includes('/link/members')) {
        return Promise.resolve({
          ok: true,
          json: async () => ({ members: [], branchToken: 'tok-server' }),
        });
      }
      if (url.includes('/students/search')) {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            results: [
              {
                studentId: 'stu-new',
                firstName: 'Aruzhan',
                lastName: 'A',
                branchName: 'Debut',
                type: 'student',
              },
            ],
          }),
        });
      }
      return Promise.resolve({ ok: false, json: async () => ({}) });
    });

    renderAdd();
    fireEvent.click(
      screen.getByRole('button', {
        name: new RegExp(en.ceTournaments.addFamilyMember),
      }),
    );

    // The server-resolved token scopes the search on a device with no stashed
    // branch-welcome URL.
    const input = await screen.findByLabelText(
      en.ceTournaments.addMemberSearchPlaceholder,
    );
    fireEvent.change(input, { target: { value: 'aru' } });
    const result = await screen.findByRole('button', { name: /Aruzhan/ });
    expect(result).toBeTruthy();
    expect(
      fetchMock.mock.calls.some((c) =>
        String(c[0]).includes('branchToken=tok-server'),
      ),
    ).toBe(true);
  });

  it('online account: renders the mint form (no search) and posts to /online/family', async () => {
    localStorage.clear();
    fetchMock.mockImplementation((url: string, opts?: RequestInit) => {
      if (url.includes('/link/members')) {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            members: [
              {
                studentId: 'stu-self',
                name: 'Online Parent',
                relationship: 'self',
                status: 'verified',
                source: 'online',
              },
            ],
            branchToken: null,
          }),
        });
      }
      if (url.includes('/online/family')) {
        expect(opts?.method).toBe('POST');
        expect(JSON.parse(String(opts?.body))).toEqual({
          name: 'Sam',
          relationship: 'child',
        });
        return Promise.resolve({
          ok: true,
          json: async () => ({ ok: true, studentId: 'stu-new' }),
        });
      }
      return Promise.resolve({ ok: false, json: async () => ({}) });
    });

    renderAdd();
    fireEvent.click(
      screen.getByRole('button', {
        name: new RegExp(en.ceTournaments.addFamilyMember),
      }),
    );

    // Online mode shows a name field — and NEVER the roster search box.
    const nameInput = await screen.findByLabelText(
      en.ceTournaments.addMemberNamePlaceholder,
    );
    expect(
      screen.queryByLabelText(en.ceTournaments.addMemberSearchPlaceholder),
    ).toBeNull();

    fireEvent.change(nameInput, { target: { value: 'Sam' } });
    fireEvent.click(
      screen.getByRole('button', { name: en.ceTournaments.addMemberSubmit }),
    );

    await waitFor(() => {
      expect(
        fetchMock.mock.calls.some((c) => String(c[0]).includes('/online/family')),
      ).toBe(true);
    });
    expect(refreshMock).toHaveBeenCalled();
  });

  it('explains when neither device storage nor the server yields a branch token', async () => {
    localStorage.clear();
    fetchMock.mockImplementation((url: string) => {
      if (url.includes('/link/members')) {
        return Promise.resolve({
          ok: true,
          json: async () => ({ members: [], branchToken: null }),
        });
      }
      return Promise.resolve({ ok: false, json: async () => ({}) });
    });

    renderAdd();
    fireEvent.click(
      screen.getByRole('button', {
        name: new RegExp(en.ceTournaments.addFamilyMember),
      }),
    );
    expect(
      await screen.findByText(en.ceTournaments.addMemberUnavailable),
    ).toBeTruthy();
  });
});
