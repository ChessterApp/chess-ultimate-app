/**
 * @vitest-environment jsdom
 *
 * LiveGameGuard (phase 6): the page-level auth guard for /play/live/* on tenant
 * hosts. Signed-out visitors are redirected to the apex sign-in with a
 * redirect_url back to the exact game URL; signed-in users pass through with no
 * redirect (a no-op on chesster.io, where middleware already enforces auth).
 */
import { describe, it, expect, afterEach, beforeEach, vi } from 'vitest';
import React from 'react';
import { cleanup, render } from '@testing-library/react';

const { userState } = vi.hoisted(() => ({
  userState: { isLoaded: true, isSignedIn: false } as { isLoaded: boolean; isSignedIn: boolean },
}));

vi.mock('@clerk/nextjs', () => ({
  useUser: () => userState,
}));

vi.mock('next/font/google', () => ({
  Fredoka: () => ({ style: { fontFamily: 'Fredoka' }, variable: 'fredoka', className: 'fredoka' }),
  Nunito: () => ({ style: { fontFamily: 'Nunito' }, variable: 'nunito', className: 'nunito' }),
}));

import LiveGameGuard from '../LiveGameGuard';

const assign = vi.fn();

function setLocation(hostname: string, href: string) {
  Object.defineProperty(window, 'location', {
    configurable: true,
    value: { hostname, href, assign },
  });
}

const child = <div data-testid="game-child">game</div>;

beforeEach(() => {
  assign.mockReset();
  userState.isLoaded = true;
  userState.isSignedIn = false;
});

afterEach(cleanup);

describe('LiveGameGuard', () => {
  it('signed-out on a tenant host redirects to the apex sign-in with the game as redirect_url', () => {
    userState.isSignedIn = false;
    setLocation('chess-empire.chesster.io', 'https://chess-empire.chesster.io/play/live/abc');

    const { queryByTestId, getByTestId } = render(<LiveGameGuard>{child}</LiveGameGuard>);

    const expected =
      'https://chesster.io/sign-in?redirect_url=' +
      encodeURIComponent('https://chess-empire.chesster.io/play/live/abc');
    expect(assign).toHaveBeenCalledWith(expected);
    // Children never mount for a signed-out visitor.
    expect(queryByTestId('game-child')).toBeNull();
    expect(getByTestId('live-game-auth-loading')).toBeTruthy();
  });

  it('signed-out on the apex host uses a relative sign-in path (same origin)', () => {
    userState.isSignedIn = false;
    setLocation('chesster.io', 'https://chesster.io/play/live/abc');

    render(<LiveGameGuard>{child}</LiveGameGuard>);

    expect(assign).toHaveBeenCalledWith(
      '/sign-in?redirect_url=' + encodeURIComponent('https://chesster.io/play/live/abc'),
    );
  });

  it('signed-in renders children and never redirects (no double-redirect on chesster.io)', () => {
    userState.isSignedIn = true;
    setLocation('chesster.io', 'https://chesster.io/play/live/abc');

    const { getByTestId } = render(<LiveGameGuard>{child}</LiveGameGuard>);

    expect(getByTestId('game-child')).toBeTruthy();
    expect(assign).not.toHaveBeenCalled();
  });

  it('while Clerk is still loading, holds on the loading card without redirecting', () => {
    userState.isLoaded = false;
    userState.isSignedIn = false;
    setLocation('chess-empire.chesster.io', 'https://chess-empire.chesster.io/play/live/abc');

    const { getByTestId, queryByTestId } = render(<LiveGameGuard>{child}</LiveGameGuard>);

    expect(getByTestId('live-game-auth-loading')).toBeTruthy();
    expect(queryByTestId('game-child')).toBeNull();
    expect(assign).not.toHaveBeenCalled();
  });
});
