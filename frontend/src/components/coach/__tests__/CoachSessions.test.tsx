/**
 * @vitest-environment jsdom
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup, fireEvent, within, waitFor } from '@testing-library/react';
import { NextIntlClientProvider } from 'next-intl';

import en from '../../../../messages/en.json';

const api = vi.hoisted(() => ({
  listSessions: vi.fn(),
  updateSession: vi.fn(),
  deleteSession: vi.fn(),
}));
vi.mock('@/lib/coach/boards-api', () => ({ coachApi: api }));

import CoachSessions from '../CoachSessions';

const coach = en.coach;

const session = (id: string, title: string) => ({
  id,
  title,
  preview: '',
  updated_at: 1_700_000_000,
  message_count: 3,
});

function renderSessions(props: Partial<React.ComponentProps<typeof CoachSessions>> = {}) {
  const handlers = { onSelect: vi.fn(), onNew: vi.fn(), onClose: vi.fn() };
  render(
    <NextIntlClientProvider locale="en" messages={en as Record<string, unknown>}>
      <CoachSessions currentSessionId="s1" {...handlers} {...props} />
    </NextIntlClientProvider>,
  );
  return handlers;
}

beforeEach(() => {
  vi.clearAllMocks();
  api.listSessions.mockResolvedValue([session('s1', 'Sicilian'), session('s2', 'Endgames')]);
  api.updateSession.mockImplementation(async (id: string, patch: { title: string }) => ({ ...session(id, ''), ...patch }));
  api.deleteSession.mockResolvedValue(true);
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

async function openMenu(title: string) {
  const row = (await screen.findByText(title)).closest('li')!;
  fireEvent.click(within(row).getByRole('button', { name: coach.sessionActions }));
  return within(row).getByRole('menu');
}

describe('CoachSessions — touch-friendly row actions', () => {
  it('every row has a visible ⋯ button with a 44px tap target', async () => {
    renderSessions();
    await screen.findByText('Sicilian');
    const buttons = screen.getAllByRole('button', { name: coach.sessionActions });
    expect(buttons).toHaveLength(2);
    for (const b of buttons) {
      expect(b.className).toContain('h-11');
      expect(b.className).toContain('w-11');
      expect(b.className).not.toContain('opacity-0');
    }
  });

  it('opening the menu does not switch to that session', async () => {
    const { onSelect } = renderSessions();
    const menu = await openMenu('Endgames');
    expect(within(menu).getByText(coach.renameSession)).toBeTruthy();
    expect(within(menu).getByText(coach.deleteSession)).toBeTruthy();
    expect(onSelect).not.toHaveBeenCalled();
  });

  it('renames through a styled dialog — Enter saves, no window.prompt', async () => {
    const promptSpy = vi.spyOn(window, 'prompt');
    renderSessions();
    fireEvent.click(within(await openMenu('Endgames')).getByText(coach.renameSession));
    const dialog = screen.getByRole('dialog', { name: coach.renameSession });
    const field = within(dialog).getByRole('textbox') as HTMLInputElement;
    expect(field.value).toBe('Endgames');
    expect(document.activeElement).toBe(field);
    fireEvent.change(field, { target: { value: 'Rook endgames' } });
    fireEvent.submit(field.form!);
    await waitFor(() => expect(api.updateSession).toHaveBeenCalledWith('s2', { title: 'Rook endgames' }));
    expect(await screen.findByText('Rook endgames')).toBeTruthy();
    expect(promptSpy).not.toHaveBeenCalled();
  });

  it('Esc cancels a rename', async () => {
    renderSessions();
    fireEvent.click(within(await openMenu('Sicilian')).getByText(coach.renameSession));
    fireEvent.keyDown(screen.getByRole('dialog', { name: coach.renameSession }), { key: 'Escape' });
    await waitFor(() => expect(screen.queryByRole('dialog', { name: coach.renameSession })).toBeNull());
    expect(api.updateSession).not.toHaveBeenCalled();
  });

  it('deletes after confirming in a styled dialog, no window.confirm', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm');
    const { onNew } = renderSessions();
    fireEvent.click(within(await openMenu('Sicilian')).getByText(coach.deleteSession));
    const dialog = screen.getByRole('dialog', { name: coach.deleteSession });
    expect(dialog.textContent).toContain('Sicilian');
    fireEvent.click(within(dialog).getByRole('button', { name: coach.delete }));
    await waitFor(() => expect(api.deleteSession).toHaveBeenCalledWith('s1'));
    await waitFor(() => expect(screen.queryByText('Sicilian')).toBeNull());
    // Deleting the open session starts a new one.
    expect(onNew).toHaveBeenCalled();
    expect(confirmSpy).not.toHaveBeenCalled();
  });

  it('cancelling the delete dialog keeps the session', async () => {
    renderSessions();
    fireEvent.click(within(await openMenu('Endgames')).getByText(coach.deleteSession));
    fireEvent.click(within(screen.getByRole('dialog', { name: coach.deleteSession })).getByText(coach.cancel));
    await waitFor(() => expect(screen.queryByRole('dialog', { name: coach.deleteSession })).toBeNull());
    expect(api.deleteSession).not.toHaveBeenCalled();
    expect(screen.getByText('Endgames')).toBeTruthy();
  });
});
