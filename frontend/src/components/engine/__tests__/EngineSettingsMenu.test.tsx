/**
 * @vitest-environment jsdom
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { render, screen, fireEvent, cleanup, within } from '@testing-library/react';
import { NextIntlClientProvider } from 'next-intl';
import en from '../../../../messages/en.json';
import EngineSettingsMenu from '../EngineSettingsMenu';
import { ENGINE_DISPLAY_STORAGE_KEY } from '@/hooks/useEngineDisplaySettings';

function renderMenu(parentClick = vi.fn()) {
  render(
    <NextIntlClientProvider locale="en" messages={en as Record<string, unknown>}>
      <div onClick={parentClick}>
        <EngineSettingsMenu extra={<span>extra-slot</span>} />
      </div>
    </NextIntlClientProvider>,
  );
  return parentClick;
}

const stored = () => JSON.parse(window.localStorage.getItem(ENGINE_DISPLAY_STORAGE_KEY) ?? 'null');

describe('EngineSettingsMenu', () => {
  beforeEach(() => window.localStorage.clear());
  afterEach(cleanup);

  it('opens a popover with depth and lines groups on click', () => {
    renderMenu();
    expect(screen.queryByRole('group', { name: 'Depth' })).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: 'Engine settings' }));
    const depth = screen.getByRole('group', { name: 'Depth' });
    expect(within(depth).getAllByRole('button').map((b) => b.textContent)).toEqual(['12', '16', '18', '20', '24']);
    const lines = screen.getByRole('group', { name: 'Lines' });
    expect(within(lines).getAllByRole('button').map((b) => b.textContent)).toEqual(['1', '2', '3', '4', '5']);
    expect(within(depth).getByRole('button', { name: '18' }).getAttribute('aria-pressed')).toBe('true');
    expect(within(lines).getByRole('button', { name: '1' }).getAttribute('aria-pressed')).toBe('true');
    expect(screen.getByText('extra-slot')).toBeTruthy();
  });

  it('selecting depth / lines updates the shared settings', () => {
    renderMenu();
    fireEvent.click(screen.getByRole('button', { name: 'Engine settings' }));
    fireEvent.click(within(screen.getByRole('group', { name: 'Depth' })).getByRole('button', { name: '24' }));
    fireEvent.click(within(screen.getByRole('group', { name: 'Lines' })).getByRole('button', { name: '3' }));
    expect(stored()).toEqual({ depth: 24, lines: 3 });
    const depth24 = within(screen.getByRole('group', { name: 'Depth' })).getByRole('button', { name: '24' });
    expect(depth24.getAttribute('aria-pressed')).toBe('true');
  });

  it('clicking the gear does not propagate to a parent onClick', () => {
    const parentClick = renderMenu();
    fireEvent.click(screen.getByRole('button', { name: 'Engine settings' }));
    expect(parentClick).not.toHaveBeenCalled();
  });
});
