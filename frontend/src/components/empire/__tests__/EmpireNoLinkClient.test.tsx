/**
 * @vitest-environment jsdom
 *
 * Behavior tests for the no_link polling client:
 *   - replays a stored invite JWT to /link/claim on mount, refreshing on success
 *   - clears storage only on a signature-class (`invalid`) terminal error
 *   - does NOT wipe the stored JWT on an expiry 410 (server may accept it later)
 *   - retries the claim + poll on every fresh mount (remount restarts polling)
 *   - polls /link/status and refreshes when the state leaves no_link
 *   - shows the spinner while polling
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, cleanup } from '@testing-library/react';

const refresh = vi.fn();
vi.mock('next/navigation', () => ({ useRouter: () => ({ refresh }) }));
vi.mock('next-intl', () => ({ useTranslations: () => (k: string) => k }));

import EmpireNoLinkClient from '../EmpireNoLinkClient';
import { CE_INVITE_JWT_STORAGE_KEY as KEY } from '@/lib/invite-storage';

const fetchMock = vi.fn();

function jsonRes(status: number, body: unknown) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as Response;
}

const Static = () => <div data-testid="static-message">static</div>;

beforeEach(() => {
  refresh.mockClear();
  fetchMock.mockReset();
  vi.stubGlobal('fetch', fetchMock);
  sessionStorage.clear();
  localStorage.clear();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe('EmpireNoLinkClient', () => {
  it('shows the setting-up spinner while polling', async () => {
    fetchMock.mockResolvedValue(jsonRes(200, { state: 'no_link' }));
    render(
      <EmpireNoLinkClient>
        <Static />
      </EmpireNoLinkClient>,
    );
    expect(screen.getByTestId('empire-home-nolink-polling')).toBeTruthy();
    expect(screen.getByText('settingUpProfile')).toBeTruthy();
  });

  it('replays a stored JWT to /link/claim and refreshes on success', async () => {
    localStorage.setItem(KEY, 'stored.jwt.tok');
    fetchMock.mockImplementation((url: string) =>
      Promise.resolve(
        String(url).includes('/claim')
          ? jsonRes(200, { ok: true, state: 'verified' })
          : jsonRes(200, { state: 'no_link' }),
      ),
    );

    render(
      <EmpireNoLinkClient>
        <Static />
      </EmpireNoLinkClient>,
    );

    await waitFor(() => expect(refresh).toHaveBeenCalled());
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/chess-empire/link/claim',
      expect.objectContaining({ method: 'POST' }),
    );
    expect(localStorage.getItem(KEY)).toBeNull();
    // Refresh + stop → the static child renders.
    await waitFor(() => expect(screen.getByTestId('static-message')).toBeTruthy());
  });

  it('clears storage on a signature-class (invalid) terminal error and keeps polling', async () => {
    localStorage.setItem(KEY, 'bad.sig.tok');
    sessionStorage.setItem(KEY, 'bad.sig.tok');
    fetchMock.mockImplementation((url: string) =>
      Promise.resolve(
        String(url).includes('/claim')
          ? jsonRes(400, { error: 'invalid', terminal: true })
          : jsonRes(200, { state: 'no_link' }),
      ),
    );

    render(
      <EmpireNoLinkClient>
        <Static />
      </EmpireNoLinkClient>,
    );

    await waitFor(() => expect(localStorage.getItem(KEY)).toBeNull());
    expect(sessionStorage.getItem(KEY)).toBeNull();
    expect(refresh).not.toHaveBeenCalled();
    expect(screen.getByTestId('empire-home-nolink-polling')).toBeTruthy();
  });

  it('does NOT wipe the stored JWT on an expiry 410 (server may accept it later)', async () => {
    localStorage.setItem(KEY, 'expired.jwt.tok');
    sessionStorage.setItem(KEY, 'expired.jwt.tok');
    let claimCalls = 0;
    fetchMock.mockImplementation((url: string) => {
      if (String(url).includes('/claim')) {
        claimCalls += 1;
        return Promise.resolve(jsonRes(410, { error: 'expired', terminal: true }));
      }
      return Promise.resolve(jsonRes(200, { state: 'no_link' }));
    });

    render(
      <EmpireNoLinkClient>
        <Static />
      </EmpireNoLinkClient>,
    );

    await waitFor(() => expect(claimCalls).toBeGreaterThan(0));
    // Expiry is recoverable — the JWT must survive for the next attempt.
    expect(localStorage.getItem(KEY)).toBe('expired.jwt.tok');
    expect(sessionStorage.getItem(KEY)).toBe('expired.jwt.tok');
    expect(refresh).not.toHaveBeenCalled();
    expect(screen.getByTestId('empire-home-nolink-polling')).toBeTruthy();
  });

  it('retries the claim + poll on a fresh mount (remount restarts polling)', async () => {
    localStorage.setItem(KEY, 'stored.jwt.tok');
    fetchMock.mockImplementation((url: string) =>
      Promise.resolve(
        String(url).includes('/claim')
          ? jsonRes(410, { error: 'expired', terminal: true })
          : jsonRes(200, { state: 'no_link' }),
      ),
    );

    const first = render(
      <EmpireNoLinkClient>
        <Static />
      </EmpireNoLinkClient>,
    );
    await waitFor(() =>
      expect(
        fetchMock.mock.calls.some((c) => String(c[0]).includes('/claim')),
      ).toBe(true),
    );
    await waitFor(() =>
      expect(
        fetchMock.mock.calls.some((c) => String(c[0]).includes('/status')),
      ).toBe(true),
    );

    // Unmount and remount — a fresh page load must retry both the claim and poll.
    first.unmount();
    fetchMock.mockClear();

    render(
      <EmpireNoLinkClient>
        <Static />
      </EmpireNoLinkClient>,
    );
    await waitFor(() =>
      expect(
        fetchMock.mock.calls.some((c) => String(c[0]).includes('/claim')),
      ).toBe(true),
    );
    await waitFor(() =>
      expect(
        fetchMock.mock.calls.some((c) => String(c[0]).includes('/status')),
      ).toBe(true),
    );
  });

  it('polls /link/status and refreshes when the state leaves no_link', async () => {
    // No stored JWT → claim is skipped, straight to polling.
    fetchMock.mockImplementation((url: string) =>
      Promise.resolve(
        String(url).includes('/status')
          ? jsonRes(200, { state: 'verified' })
          : jsonRes(200, {}),
      ),
    );

    render(
      <EmpireNoLinkClient>
        <Static />
      </EmpireNoLinkClient>,
    );

    await waitFor(() => expect(refresh).toHaveBeenCalled());
    const claimCalled = fetchMock.mock.calls.some((c) =>
      String(c[0]).includes('/claim'),
    );
    expect(claimCalled).toBe(false);
  });
});
