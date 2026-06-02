/**
 * @vitest-environment jsdom
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import React from 'react';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import DeleteSchoolCard from '../DeleteSchoolCard';

const ORG_ID = 'org-uuid-1';
const ORG_NAME = 'Almaty Chess Academy';

describe('<DeleteSchoolCard />', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    cleanup();
  });

  it('renders the idle danger card when no deletion is scheduled', () => {
    render(
      <DeleteSchoolCard
        orgId={ORG_ID}
        orgName={ORG_NAME}
        initialDeletionRequestedAt={null}
      />,
    );
    expect(screen.getByTestId('delete-school-card')).toBeTruthy();
    expect(screen.getByText('Delete school')).toBeTruthy();
    expect(screen.getByRole('button', { name: /delete this school/i })).toBeTruthy();
    expect(screen.queryByTestId('delete-school-scheduled')).toBeNull();
  });

  it('renders the scheduled state when deletionRequestedAt is set', () => {
    render(
      <DeleteSchoolCard
        orgId={ORG_ID}
        orgName={ORG_NAME}
        initialDeletionRequestedAt="2026-06-01T12:00:00Z"
      />,
    );
    expect(screen.getByTestId('delete-school-scheduled')).toBeTruthy();
    expect(screen.getByText(/Deletion scheduled/i)).toBeTruthy();
    expect(screen.getByText(/support@chesster.io/i)).toBeTruthy();
    // No idle card, no "Delete this school" button in scheduled state.
    expect(screen.queryByTestId('delete-school-card')).toBeNull();
    expect(screen.queryByRole('button', { name: /delete this school/i })).toBeNull();
  });

  it('opens the confirmation modal when "Delete this school" is clicked', () => {
    render(
      <DeleteSchoolCard
        orgId={ORG_ID}
        orgName={ORG_NAME}
        initialDeletionRequestedAt={null}
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: /delete this school/i }));
    expect(screen.getByTestId('delete-school-modal')).toBeTruthy();
    expect(screen.getByText(`Delete ${ORG_NAME}?`)).toBeTruthy();
  });

  it('disables the final delete button until the typed name matches exactly', () => {
    render(
      <DeleteSchoolCard
        orgId={ORG_ID}
        orgName={ORG_NAME}
        initialDeletionRequestedAt={null}
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: /delete this school/i }));
    const finalBtn = screen.getByRole('button', {
      name: /^delete school$/i,
    }) as HTMLButtonElement;
    expect(finalBtn.disabled).toBe(true);

    const input = screen.getByLabelText(/type "/i) as HTMLInputElement;
    // Partial match → still disabled
    fireEvent.change(input, { target: { value: 'Almaty' } });
    expect(finalBtn.disabled).toBe(true);

    // Exact match → enabled
    fireEvent.change(input, { target: { value: ORG_NAME } });
    expect(finalBtn.disabled).toBe(false);
  });

  it('POSTs to the delete-request endpoint and shows scheduled state on success', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        ok: true,
        deletion_requested_at: '2026-06-02T08:30:00Z',
      }),
    });
    vi.stubGlobal('fetch', fetchMock);

    render(
      <DeleteSchoolCard
        orgId={ORG_ID}
        orgName={ORG_NAME}
        initialDeletionRequestedAt={null}
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: /delete this school/i }));
    fireEvent.change(screen.getByLabelText(/type "/i), {
      target: { value: ORG_NAME },
    });
    fireEvent.click(screen.getByRole('button', { name: /^delete school$/i }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe(`/api/admin/organizations/${ORG_ID}/delete-request`);
    expect(init.method).toBe('POST');
    expect(JSON.parse(init.body)).toEqual({ confirm_name: ORG_NAME });

    // After a successful response → scheduled state replaces the card.
    await waitFor(() =>
      expect(screen.getByTestId('delete-school-scheduled')).toBeTruthy(),
    );
    expect(screen.queryByTestId('delete-school-card')).toBeNull();
  });

  it('renders an error message when the server rejects the request', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: false,
      json: async () => ({ error: 'confirm_name does not match' }),
    });
    vi.stubGlobal('fetch', fetchMock);

    render(
      <DeleteSchoolCard
        orgId={ORG_ID}
        orgName={ORG_NAME}
        initialDeletionRequestedAt={null}
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: /delete this school/i }));
    fireEvent.change(screen.getByLabelText(/type "/i), {
      target: { value: ORG_NAME },
    });
    fireEvent.click(screen.getByRole('button', { name: /^delete school$/i }));

    await waitFor(() =>
      expect(screen.getByTestId('delete-school-error').textContent).toMatch(
        /confirm_name does not match/i,
      ),
    );
    // Still in idle state — no scheduled card.
    expect(screen.queryByTestId('delete-school-scheduled')).toBeNull();
  });

  it('cancels the modal without calling the API', () => {
    const fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);

    render(
      <DeleteSchoolCard
        orgId={ORG_ID}
        orgName={ORG_NAME}
        initialDeletionRequestedAt={null}
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: /delete this school/i }));
    fireEvent.change(screen.getByLabelText(/type "/i), {
      target: { value: ORG_NAME },
    });
    fireEvent.click(screen.getByRole('button', { name: /cancel/i }));

    expect(fetchMock).not.toHaveBeenCalled();
    expect(screen.queryByTestId('delete-school-modal')).toBeNull();
  });
});
