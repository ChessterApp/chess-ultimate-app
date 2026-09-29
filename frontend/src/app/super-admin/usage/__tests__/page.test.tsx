// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import React from 'react';
import CoachUsagePage from '../page';
import { aggregateUsage, resolvePeriod } from '@/lib/coach-usage';

function report(period: '7d' | 'today') {
  const p = resolvePeriod(period);
  const now = new Date().toISOString();
  return aggregateUsage(
    [
      { user_id: 'user_a', surface: 'text', model: 'deepseek/deepseek-v4.1-flash', prompt_tokens: 100,
        completion_tokens: 20, estimated_cost_usd: 0.25, turn_id: 't1', created_at: now },
      { user_id: 'user_b', surface: 'voice', model: 'gemini-3.1-flash-live-preview', prompt_tokens: 100,
        completion_tokens: 20, estimated_cost_usd: 1.5, turn_id: 'v1', created_at: now },
    ],
    null,
    new Map([
      ['user_a', { name: 'Алия', email: 'aliya@example.com', schools: ['Chess Empire'] }],
      ['user_b', { name: 'Тимур', email: 'timur@example.com', schools: [] }],
    ]),
    p,
  );
}

beforeEach(() => {
  global.fetch = vi.fn(async (url: string) => ({
    ok: true,
    json: async () => report(String(url).includes('today') ? 'today' : '7d'),
  })) as unknown as typeof fetch;
});

describe('/super-admin/usage', () => {
  it('lists students by spend with the totals', async () => {
    render(<CoachUsagePage />);
    await waitFor(() => expect(screen.getByText('Тимур')).toBeTruthy());
    const rows = screen.getByTestId('usage-table').querySelectorAll('tbody tr');
    expect(rows[0].textContent).toContain('Тимур'); // the bigger spender first
    expect(rows[1].textContent).toContain('Алия');
    expect(screen.getAllByText('$1.75').length).toBeGreaterThan(0);
    expect(global.fetch).toHaveBeenCalledWith('/api/admin/coach-usage?period=7d', expect.anything());
  });

  it('switches the period and filters by search', async () => {
    render(<CoachUsagePage />);
    await waitFor(() => screen.getByText('Алия'));
    fireEvent.click(screen.getByRole('tab', { name: 'Сегодня' }));
    await waitFor(() =>
      expect(global.fetch).toHaveBeenCalledWith('/api/admin/coach-usage?period=today', expect.anything()),
    );
    fireEvent.change(screen.getByPlaceholderText(/Поиск/), { target: { value: 'empire' } });
    await waitFor(() => expect(screen.queryByText('Тимур')).toBeNull());
    expect(screen.getByText('Алия')).toBeTruthy();
  });

  it('opens a student with the models behind the spend', async () => {
    render(<CoachUsagePage />);
    await waitFor(() => screen.getByText('Алия'));
    fireEvent.click(screen.getByText('Алия'));
    expect(screen.getAllByText('deepseek/deepseek-v4.1-flash').length).toBeGreaterThan(1);
  });

  it('shows the error from the server', async () => {
    global.fetch = vi.fn(async () => ({ ok: false, status: 403, json: async () => ({ error: 'Forbidden' }) })) as never;
    render(<CoachUsagePage />);
    await waitFor(() => expect(screen.getByText('Forbidden')).toBeTruthy());
  });
});
