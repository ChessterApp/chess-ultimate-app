/**
 * @vitest-environment jsdom
 *
 * Client state-machine tests for WelcomeFlow. Mocks `fetch` and the Next
 * router; walks the search → confirm → DOB happy path and the failure
 * branches (no results, wrong DOB ≥3 times, 409 already-registered).
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import React from 'react';
import { act, cleanup, fireEvent, render, waitFor } from '@testing-library/react';

const routerReplace = vi.fn();

vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace: routerReplace, push: vi.fn() }),
}));

vi.mock('next-intl', () => ({
  useTranslations: () => (key: string, opts?: Record<string, unknown>) =>
    opts ? `${key}:${Object.values(opts).join(',')}` : key,
}));

vi.mock('next/image', () => ({
  default: ({ alt, src }: { alt: string; src: string }) => (
    // eslint-disable-next-line @next/next/no-img-element
    <img alt={alt} src={src} />
  ),
}));

vi.mock('@/contexts/OrganizationContext', () => ({
  useBranding: () => ({
    name: 'Chess Empire',
    logoUrl: null,
    primaryColor: '#9333ea',
  }),
  useOrganization: () => ({ org: null, isWhiteLabel: false }),
}));

import WelcomeFlow from '../WelcomeFlow';

const sampleResults = [
  { studentId: 'stu-1', firstName: 'Aiman', lastName: 'Kassymova', branchName: 'Debut', coachName: 'Anna' },
  { studentId: 'stu-2', firstName: 'Aida', lastName: 'Bekova', branchName: 'Debut', coachName: null },
];

interface MockResponse {
  ok: boolean;
  status: number;
  json: () => Promise<unknown>;
}

function jsonResponse(body: unknown, status = 200): MockResponse {
  return { ok: status >= 200 && status < 300, status, json: async () => body };
}

interface FetchCall {
  url: string;
  init?: RequestInit;
}

let fetchCalls: FetchCall[];
let fetchHandler: (call: FetchCall) => Promise<MockResponse>;

beforeEach(() => {
  fetchCalls = [];
  fetchHandler = async () => jsonResponse({ results: [] });
  routerReplace.mockReset();
  global.fetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === 'string' ? input : input.toString();
    fetchCalls.push({ url, init });
    return (await fetchHandler({ url, init })) as unknown as Response;
  });
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.restoreAllMocks();
});

function renderFlow() {
  return render(
    <WelcomeFlow branchToken="tok-abc" branchName="Debut" organizationId="org-1" />,
  );
}

async function flushDebounce() {
  // Wait through the 250 ms debounce + a small buffer for fetch microtasks.
  // We use real timers in the flow tests because `findByTestId` / `waitFor`
  // poll with `setTimeout` and would deadlock under `vi.useFakeTimers()`.
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 320));
  });
}

describe('WelcomeFlow', () => {
  it('renders heading with branch name on initial render', () => {

    const { getByRole, container } = renderFlow();
    expect(getByRole('heading').textContent).toContain('Debut');
    expect(container.querySelector('#welcome-search')).not.toBeNull();
  });

  it('does not search for query shorter than 2 chars', async () => {

    const { container } = renderFlow();
    const input = container.querySelector('#welcome-search') as HTMLInputElement;
    fireEvent.change(input, { target: { value: 'a' } });
    await flushDebounce();
    expect(fetchCalls).toHaveLength(0);
  });

  it('searches with debounced query and shows results', async () => {

    fetchHandler = async () => jsonResponse({ results: sampleResults });
    const { container, queryByTestId } = renderFlow();
    const input = container.querySelector('#welcome-search') as HTMLInputElement;
    fireEvent.change(input, { target: { value: 'ai' } });
    await flushDebounce();
    await waitFor(() => expect(queryByTestId('welcome-search-results')).not.toBeNull());
    const list = queryByTestId('welcome-search-results')!;
    expect(list.children.length).toBe(2);
    expect(fetchCalls[0].url).toContain('/api/chess-empire/students/search');
    expect(fetchCalls[0].url).toContain('branchToken=tok-abc');
    expect(fetchCalls[0].url).toContain('q=ai');
  });

  it('shows empty state when API returns no results', async () => {

    fetchHandler = async () => jsonResponse({ results: [] });
    const { container } = renderFlow();
    const input = container.querySelector('#welcome-search') as HTMLInputElement;
    fireEvent.change(input, { target: { value: 'zz' } });
    await flushDebounce();
    await waitFor(() => {
      expect(container.textContent).toContain('noResults');
    });
  });

  it('happy path: search → confirm → DOB → /sign-up?invite', async () => {

    fetchHandler = async (call) => {
      if (call.url.includes('/search')) return jsonResponse({ results: sampleResults });
      if (call.url.includes('/verify')) return jsonResponse({ inviteJwt: 'jwt.token.sig' });
      return jsonResponse({});
    };
    const { container, findByTestId } = renderFlow();
    const input = container.querySelector('#welcome-search') as HTMLInputElement;
    fireEvent.change(input, { target: { value: 'ai' } });
    await flushDebounce();
    const list = await findByTestId('welcome-search-results');
    fireEvent.click(list.querySelectorAll('button')[0]);

    // Confirm step.
    await waitFor(() => expect(container.textContent).toContain('confirmTitle'));
    const yesButton = Array.from(container.querySelectorAll('button')).find((b) =>
      b.textContent?.includes('confirmYes'),
    )!;
    fireEvent.click(yesButton);

    // DOB step.
    await waitFor(() => expect(container.textContent).toContain('dobTitle'));
    const inputs = container.querySelectorAll<HTMLInputElement>('input[inputmode="numeric"]');
    expect(inputs).toHaveLength(3);
    fireEvent.change(inputs[0], { target: { value: '15' } });
    fireEvent.change(inputs[1], { target: { value: '07' } });
    fireEvent.change(inputs[2], { target: { value: '2012' } });

    const verifyButton = Array.from(container.querySelectorAll('button')).find((b) =>
      b.textContent?.includes('verifyButton'),
    ) as HTMLButtonElement;
    expect(verifyButton.disabled).toBe(false);
    await act(async () => {
      fireEvent.click(verifyButton);
    });

    await waitFor(() => {
      const verifyCall = fetchCalls.find((c) => c.url.includes('/verify'));
      expect(verifyCall).toBeDefined();
      const body = JSON.parse(verifyCall!.init!.body as string);
      expect(body).toEqual({
        branchToken: 'tok-abc',
        studentId: 'stu-1',
        dob: '2012-07-15',
      });
    });
    await waitFor(() => {
      expect(routerReplace).toHaveBeenCalledWith('/sign-up?invite=jwt.token.sig');
    });
  });

  it('shows DOB error and locks after 3 failed attempts', async () => {

    fetchHandler = async (call) => {
      if (call.url.includes('/search')) return jsonResponse({ results: sampleResults });
      if (call.url.includes('/verify')) return jsonResponse({ error: 'wrong_dob' }, 401);
      return jsonResponse({});
    };
    const { container, findByTestId } = renderFlow();
    const input = container.querySelector('#welcome-search') as HTMLInputElement;
    fireEvent.change(input, { target: { value: 'ai' } });
    await flushDebounce();
    const list = await findByTestId('welcome-search-results');
    fireEvent.click(list.querySelectorAll('button')[0]);
    const yesButton = Array.from(container.querySelectorAll('button')).find((b) =>
      b.textContent?.includes('confirmYes'),
    )!;
    fireEvent.click(yesButton);

    const inputs = () => container.querySelectorAll<HTMLInputElement>('input[inputmode="numeric"]');
    await waitFor(() => expect(inputs()).toHaveLength(3));

    async function submitDob(day: string, month: string, year: string) {
      const ins = inputs();
      fireEvent.change(ins[0], { target: { value: day } });
      fireEvent.change(ins[1], { target: { value: month } });
      fireEvent.change(ins[2], { target: { value: year } });
      const verifyButton = Array.from(container.querySelectorAll('button')).find((b) =>
        b.textContent && (b.textContent.includes('verifyButton') || b.textContent.includes('verifying')),
      ) as HTMLButtonElement;
      await act(async () => {
        fireEvent.click(verifyButton);
      });
    }

    await submitDob('01', '01', '2000');
    await waitFor(() => expect(container.textContent).toContain('dobError'));
    await submitDob('02', '02', '2001');
    await submitDob('03', '03', '2002');

    await waitFor(() => expect(container.textContent).toContain('tooManyAttempts'));
    const verifyButton = Array.from(container.querySelectorAll('button')).find((b) =>
      b.textContent?.includes('verifyButton'),
    ) as HTMLButtonElement;
    expect(verifyButton.disabled).toBe(true);
  });

  it('redirects to /registered on 409 ALREADY_REGISTERED', async () => {

    fetchHandler = async (call) => {
      if (call.url.includes('/search')) return jsonResponse({ results: sampleResults });
      if (call.url.includes('/verify')) return jsonResponse({ error: 'ALREADY_REGISTERED' }, 409);
      return jsonResponse({});
    };
    const { container, findByTestId } = renderFlow();
    const input = container.querySelector('#welcome-search') as HTMLInputElement;
    fireEvent.change(input, { target: { value: 'ai' } });
    await flushDebounce();
    const list = await findByTestId('welcome-search-results');
    fireEvent.click(list.querySelectorAll('button')[0]);
    const yesButton = Array.from(container.querySelectorAll('button')).find((b) =>
      b.textContent?.includes('confirmYes'),
    )!;
    fireEvent.click(yesButton);

    await waitFor(() =>
      expect(container.querySelectorAll<HTMLInputElement>('input[inputmode="numeric"]')).toHaveLength(3),
    );
    const ins = container.querySelectorAll<HTMLInputElement>('input[inputmode="numeric"]');
    fireEvent.change(ins[0], { target: { value: '15' } });
    fireEvent.change(ins[1], { target: { value: '07' } });
    fireEvent.change(ins[2], { target: { value: '2012' } });
    const verifyButton = Array.from(container.querySelectorAll('button')).find((b) =>
      b.textContent?.includes('verifyButton'),
    ) as HTMLButtonElement;
    await act(async () => {
      fireEvent.click(verifyButton);
    });

    await waitFor(() => {
      expect(routerReplace).toHaveBeenCalledWith('/welcome/tok-abc/registered');
    });
  });
});
