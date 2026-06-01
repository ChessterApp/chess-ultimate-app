/**
 * @vitest-environment jsdom
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import React from 'react';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import SuperAdminSchoolsPage from '../page';

// Stable Clerk mock — must not produce a new object/function per render.
const stableGetToken = vi.fn().mockResolvedValue('test-token');
const stableAuth = { getToken: stableGetToken };
vi.mock('@clerk/nextjs', () => ({
  useAuth: () => stableAuth,
}));

vi.mock('next/link', () => ({
  default: ({
    children,
    href,
    ...props
  }: {
    children: React.ReactNode;
    href: string;
    [k: string]: unknown;
  }) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

interface SchoolRow {
  id: string;
  slug: string;
  name: string;
  status: string;
  plan: string | null;
  member_count: number;
  student_count: number | null;
  custom_domain: string | null;
  custom_domain_status: string | null;
  created_at: string | null;
}

function makeRows(): SchoolRow[] {
  return [
    {
      id: 'org-1',
      slug: 'kings-academy',
      name: "King's Academy",
      status: 'active',
      plan: 'growth',
      member_count: 12,
      student_count: 8,
      custom_domain: 'play.kings.com',
      custom_domain_status: 'active',
      created_at: '2026-04-01T00:00:00Z',
    },
    {
      id: 'org-2',
      slug: 'queens-club',
      name: "Queen's Club",
      status: 'trial',
      plan: null,
      member_count: 3,
      student_count: null,
      custom_domain: null,
      custom_domain_status: null,
      created_at: '2026-05-15T00:00:00Z',
    },
  ];
}

function installFetchMock(handler: (url: string) => unknown) {
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const url = typeof input === 'string' ? input : input.toString();
    const body = handler(url);
    return {
      ok: true,
      status: 200,
      json: async () => body,
    } as Response;
  });
  // @ts-expect-error override global fetch in tests
  global.fetch = fetchMock;
  return fetchMock;
}

describe('SuperAdminSchoolsPage', () => {
  beforeEach(() => {
    stableGetToken.mockClear();
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it('renders rows from the list endpoint', async () => {
    installFetchMock(() => ({ items: makeRows(), total: 2 }));

    render(<SuperAdminSchoolsPage />);

    await waitFor(() => {
      expect(screen.getByText("King's Academy")).toBeTruthy();
      expect(screen.getByText("Queen's Club")).toBeTruthy();
    });
    expect(screen.getByText('kings-academy')).toBeTruthy();
    expect(screen.getByText('12')).toBeTruthy();
  });

  it('status filter chips toggle the status query param', async () => {
    const calls: string[] = [];
    installFetchMock((url) => {
      calls.push(url);
      return { items: [], total: 0 };
    });

    render(<SuperAdminSchoolsPage />);
    await waitFor(() => expect(calls.length).toBeGreaterThanOrEqual(1));

    const initialCalls = calls.length;
    await act(async () => {
      fireEvent.click(screen.getByText('Suspended'));
    });
    await waitFor(() => expect(calls.length).toBeGreaterThan(initialCalls));

    const lastUrl = calls[calls.length - 1];
    expect(lastUrl).toContain('status=suspended');
  });

  it('debounced search hits API after 300ms with the typed query', async () => {
    const calls: string[] = [];
    installFetchMock((url) => {
      calls.push(url);
      return { items: [], total: 0 };
    });

    vi.useFakeTimers();
    render(<SuperAdminSchoolsPage />);
    // Flush the initial fetch effect (no debounce needed for first render).
    await act(async () => {
      await Promise.resolve();
    });
    await act(async () => {
      vi.advanceTimersByTime(0);
    });
    // Wait for the initial mount fetch (using real timers transition).
    vi.useRealTimers();
    await waitFor(() => expect(calls.length).toBeGreaterThanOrEqual(1));
    const initialCount = calls.length;

    vi.useFakeTimers();
    const input = screen.getByPlaceholderText('Search by slug or name…') as HTMLInputElement;

    await act(async () => {
      fireEvent.change(input, { target: { value: 'q' } });
    });
    await act(async () => {
      fireEvent.change(input, { target: { value: 'qu' } });
    });
    await act(async () => {
      fireEvent.change(input, { target: { value: 'queen' } });
    });

    expect(calls.length).toBe(initialCount);

    await act(async () => {
      vi.advanceTimersByTime(310);
    });
    vi.useRealTimers();

    await waitFor(() => expect(calls.length).toBeGreaterThan(initialCount));
    const lastUrl = calls[calls.length - 1];
    expect(lastUrl).toContain('q=queen');
  });
});
