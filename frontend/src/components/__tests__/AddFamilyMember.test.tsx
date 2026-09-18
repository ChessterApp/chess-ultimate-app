/**
 * @vitest-environment jsdom
 *
 * Component tests for the profile avatar "Добавить члена семьи" sub-view.
 * Mocks `fetch`. Covers: the branch chip renders the branch name, the search
 * filters roster results, «Добавить» links via link-existing, and the
 * cross-branch email-invite fallback is present and posts to link/invite.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import React from 'react';
import { act, cleanup, fireEvent, render } from '@testing-library/react';

import AddFamilyMember from '../AddFamilyMember';

interface MockResponse {
  ok: boolean;
  status: number;
  json: () => Promise<unknown>;
}

function jsonResponse(body: unknown, status = 200): MockResponse {
  return { ok: status >= 200 && status < 300, status, json: async () => body };
}

const SEARCH_RESPONSE = {
  results: [
    { studentId: 'stu-1', firstName: 'Aiman', lastName: 'Kassymova', branchName: 'Debut', type: 'student' },
    { studentId: 'stu-2', firstName: 'Aida', lastName: 'Bekova', branchName: 'Debut', type: 'student' },
  ],
  branchName: 'Debut',
  branchToken: 'tok-1',
};

const EMPTY_INITIAL = { results: [], branchName: 'Debut', branchToken: 'tok-1' };

let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
  fetchMock = vi.fn();
  // Default: the first empty-query load resolves the branch chip + token.
  fetchMock.mockResolvedValue(jsonResponse(EMPTY_INITIAL));
  vi.stubGlobal('fetch', fetchMock);
  vi.useFakeTimers();
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

/** Flush the debounce timer + pending microtasks inside act(). */
async function flush(ms = 350) {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms);
  });
}

describe('AddFamilyMember', () => {
  it('renders the branch chip with the branch name', async () => {
    const { getByText } = render(<AddFamilyMember />);
    await flush(0);
    expect(getByText('Debut')).toBeTruthy();
    expect(getByText(/Филиал:/)).toBeTruthy();
    expect(fetchMock).toHaveBeenCalledWith('/api/chess-empire/link/search?q=');
  });

  it('debounced search populates branch-scoped results', async () => {
    fetchMock
      .mockResolvedValueOnce(jsonResponse(EMPTY_INITIAL)) // initial load
      .mockResolvedValueOnce(jsonResponse(SEARCH_RESPONSE)); // search
    const { getByLabelText, getByText } = render(<AddFamilyMember />);
    await flush(0);

    fireEvent.change(getByLabelText('Поиск по имени'), { target: { value: 'ai' } });
    await flush();

    expect(getByText('Aiman Kassymova')).toBeTruthy();
    expect(getByText('Aida Bekova')).toBeTruthy();
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/chess-empire/link/search?q=ai',
      expect.objectContaining({ signal: expect.anything() }),
    );
  });

  it('«Добавить» links the member via link-existing with the branch token', async () => {
    fetchMock
      .mockResolvedValueOnce(jsonResponse(EMPTY_INITIAL))
      .mockResolvedValueOnce(jsonResponse(SEARCH_RESPONSE))
      .mockResolvedValueOnce(jsonResponse({ ok: true, studentId: 'stu-1' }));
    const { getByLabelText, getByText, getAllByText } = render(<AddFamilyMember />);
    await flush(0);

    fireEvent.change(getByLabelText('Поиск по имени'), { target: { value: 'ai' } });
    await flush();

    fireEvent.click(getAllByText('Добавить')[0]);
    await flush(0);

    const linkCall = fetchMock.mock.calls.find(
      (c) => c[0] === '/api/chess-empire/link/link-existing',
    );
    expect(linkCall).toBeTruthy();
    expect(JSON.parse((linkCall![1] as RequestInit).body as string)).toEqual({
      branchToken: 'tok-1',
      studentId: 'stu-1',
      relationship: 'child',
    });
    expect(getByText('✓ Добавлен')).toBeTruthy();
  });

  it('shows the empty state when no branch member matches', async () => {
    fetchMock
      .mockResolvedValueOnce(jsonResponse(EMPTY_INITIAL))
      .mockResolvedValueOnce(jsonResponse({ results: [], branchName: 'Debut', branchToken: 'tok-1' }));
    const { getByLabelText, getByText } = render(<AddFamilyMember />);
    await flush(0);

    fireEvent.change(getByLabelText('Поиск по имени'), { target: { value: 'zz' } });
    await flush();

    expect(getByText('Никого не найдено в вашем филиале')).toBeTruthy();
  });

  it('cross-branch fallback opens the email invite and posts to link/invite', async () => {
    fetchMock
      .mockResolvedValueOnce(jsonResponse(EMPTY_INITIAL))
      .mockResolvedValueOnce(jsonResponse({ ok: true }));
    const { getByText, getByLabelText } = render(<AddFamilyMember />);
    await flush(0);

    fireEvent.click(getByText('Другой филиал? Пригласите по эл. почте →'));
    fireEvent.change(getByLabelText('Эл. почта'), { target: { value: 'p@example.com' } });
    fireEvent.click(getByText('Отправить приглашение'));
    await flush(0);

    const inviteCall = fetchMock.mock.calls.find(
      (c) => c[0] === '/api/chess-empire/link/invite',
    );
    expect(inviteCall).toBeTruthy();
    expect(JSON.parse((inviteCall![1] as RequestInit).body as string)).toEqual({
      email: 'p@example.com',
      relationship: 'child',
    });
    expect(getByText('Приглашение отправлено ✓')).toBeTruthy();
  });
});
