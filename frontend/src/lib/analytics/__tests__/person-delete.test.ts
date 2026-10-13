import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { deletePostHogPerson } from '../person-delete';

const fetchMock = vi.fn();

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status });
}

describe('deletePostHogPerson()', () => {
  beforeEach(() => {
    fetchMock.mockReset();
    vi.stubGlobal('fetch', fetchMock);
    vi.stubEnv('POSTHOG_PERSONAL_API_KEY', 'phx_test');
    vi.stubEnv('POSTHOG_PROJECT_ID', '123');
    vi.stubEnv('POSTHOG_API_HOST', '');
    vi.spyOn(console, 'info').mockImplementation(() => {});
    vi.spyOn(console, 'warn').mockImplementation(() => {});
    vi.spyOn(console, 'error').mockImplementation(() => {});
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.unstubAllEnvs();
    vi.restoreAllMocks();
  });

  it('looks the person up by distinct id, then deletes it with its events', async () => {
    fetchMock
      .mockResolvedValueOnce(json({ results: [{ id: 9, uuid: 'abc-uuid' }] }))
      .mockResolvedValueOnce(new Response(null, { status: 204 }));

    await deletePostHogPerson('user_42');

    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      'https://us.posthog.com/api/projects/123/persons/?distinct_id=user_42',
      { headers: { Authorization: 'Bearer phx_test' } },
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      'https://us.posthog.com/api/projects/123/persons/abc-uuid/?delete_events=true',
      { method: 'DELETE', headers: { Authorization: 'Bearer phx_test' } },
    );
  });

  it('honours POSTHOG_API_HOST', async () => {
    vi.stubEnv('POSTHOG_API_HOST', 'https://eu.posthog.com/');
    fetchMock.mockResolvedValueOnce(json({ results: [] }));
    await deletePostHogPerson('user_42');
    expect(fetchMock.mock.calls[0][0]).toBe(
      'https://eu.posthog.com/api/projects/123/persons/?distinct_id=user_42',
    );
  });

  it('does not DELETE when no person is found', async () => {
    fetchMock.mockResolvedValueOnce(json({ results: [] }));
    await deletePostHogPerson('user_42');
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it('skips entirely when env is missing', async () => {
    vi.stubEnv('POSTHOG_PERSONAL_API_KEY', '');
    await deletePostHogPerson('user_42');
    expect(fetchMock).not.toHaveBeenCalled();
    expect(console.warn).toHaveBeenCalled();
  });

  it('swallows API errors', async () => {
    fetchMock.mockResolvedValueOnce(json({ detail: 'nope' }, 401));
    await expect(deletePostHogPerson('user_42')).resolves.toBeUndefined();
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(console.error).toHaveBeenCalled();
  });

  it('swallows network errors', async () => {
    fetchMock.mockRejectedValueOnce(new Error('ECONNRESET'));
    await expect(deletePostHogPerson('user_42')).resolves.toBeUndefined();
  });
});
