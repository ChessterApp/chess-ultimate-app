/**
 * @vitest-environment jsdom
 *
 * The hatch moment (Phase 3): naming → commit → reveal, and the replay path.
 * Verifies the reward/identity-before-playback flow and that skipping never
 * blocks reaching the fox. CompanionAnimation falls back to its static SVG in
 * jsdom (no matchMedia), so no Lottie runtime is exercised here.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import React from 'react';
import { cleanup, render, screen, fireEvent, waitFor } from '@testing-library/react';
import { NextIntlClientProvider } from 'next-intl';

import en from '../../../../messages/en.json';
import FoxReveal from '../FoxReveal';

function renderReveal(props: Partial<React.ComponentProps<typeof FoxReveal>> = {}) {
  const onClose = vi.fn();
  const onHatch = props.onHatch ?? vi.fn();
  render(
    <NextIntlClientProvider locale="en" messages={en as Record<string, unknown>}>
      <FoxReveal mode="hatch" onHatch={onHatch} onClose={onClose} {...props} />
    </NextIntlClientProvider>,
  );
  return { onClose, onHatch };
}

beforeEach(() => vi.clearAllMocks());
afterEach(() => cleanup());

describe('FoxReveal — hatch flow', () => {
  it('names, commits (reward before playback), then reveals the fox', async () => {
    const onHatch = vi.fn().mockResolvedValue({
      ok: true,
      name: 'Rusty',
      reward_granted: true,
      xp: 50,
      coins: 20,
      starter_granted: true,
    });
    renderReveal({ onHatch });

    // Naming step is shown first.
    const input = screen.getByLabelText(en.companion.hatch.nameLabel);
    fireEvent.change(input, { target: { value: 'Rusty' } });
    fireEvent.click(screen.getByText(en.companion.hatch.confirm));

    // Commit happens before any reveal playback.
    await waitFor(() => expect(onHatch).toHaveBeenCalledWith('Rusty'));

    // Skip the ~8s scene from the start → reward summary appears.
    fireEvent.click(await screen.findByText(en.companion.hatch.skip));
    expect(
      await screen.findByText(
        en.companion.hatch.title.replace('{name}', 'Rusty'),
      ),
    ).toBeTruthy();
    expect(
      screen.getByText(
        en.companion.hatch.reward.replace('{xp}', '50').replace('{coins}', '20'),
      ),
    ).toBeTruthy();
    expect(screen.getByText(en.companion.hatch.starter)).toBeTruthy();
  });

  it('shows a friendly message and does not reveal when the server says not-ready', async () => {
    const onHatch = vi.fn().mockResolvedValue({ ok: false, error: 'not_ready' });
    renderReveal({ onHatch });
    fireEvent.change(screen.getByLabelText(en.companion.hatch.nameLabel), {
      target: { value: 'Rusty' },
    });
    fireEvent.click(screen.getByText(en.companion.hatch.confirm));
    expect(await screen.findByText(en.companion.hatch.notReady)).toBeTruthy();
    // Still on the naming step — no reveal.
    expect(screen.queryByText(en.companion.hatch.skip)).toBeNull();
  });

  it('does not commit a blank name (button disabled)', () => {
    const onHatch = vi.fn();
    renderReveal({ onHatch });
    const btn = screen.getByText(en.companion.hatch.confirm) as HTMLButtonElement;
    expect(btn.disabled).toBe(true);
    fireEvent.click(btn);
    expect(onHatch).not.toHaveBeenCalled();
  });
});

describe('FoxReveal — replay', () => {
  it('replays the committed hatch without naming or re-granting', async () => {
    const onHatch = vi.fn();
    const onClose = vi.fn();
    render(
      <NextIntlClientProvider locale="en" messages={en as Record<string, unknown>}>
        <FoxReveal mode="replay" initialName="Rusty" onHatch={onHatch} onClose={onClose} />
      </NextIntlClientProvider>,
    );
    // No naming step; goes straight to the (skippable) scene.
    expect(screen.queryByLabelText(en.companion.hatch.nameLabel)).toBeNull();
    fireEvent.click(screen.getByText(en.companion.hatch.skip));
    expect(
      await screen.findByText(en.companion.hatch.title.replace('{name}', 'Rusty')),
    ).toBeTruthy();
    // Replay never re-commits a hatch and shows no new reward.
    expect(onHatch).not.toHaveBeenCalled();
    expect(
      screen.queryByText(
        en.companion.hatch.reward.replace('{xp}', '50').replace('{coins}', '20'),
      ),
    ).toBeNull();
    fireEvent.click(screen.getByText(en.companion.hatch.continue));
    expect(onClose).toHaveBeenCalled();
  });
});
