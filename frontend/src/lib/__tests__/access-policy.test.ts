/**
 * Unit tests for the pure access-policy module: state → policy mapping and
 * route matching for every membership state.
 */
import { describe, it, expect } from 'vitest';
import {
  getAccessPolicy,
  isRouteAllowed,
  featureKeyForPath,
  LOCKED_FEATURES,
  ALLOWED_RESTRICTED_ROUTES,
} from '../access-policy';
import type { MembershipState } from '../chess-empire-member';

describe('getAccessPolicy', () => {
  it('frozen → restricted, upgrade path /upgrade/continue', () => {
    const p = getAccessPolicy('frozen');
    expect(p.mode).toBe('restricted');
    expect(p.reason).toBe('frozen');
    expect(p.upgradePath).toBe('/upgrade/continue');
    expect(p.allowedRoutes).toEqual([...ALLOWED_RESTRICTED_ROUTES]);
  });

  it('expired → restricted, upgrade path /upgrade/expired', () => {
    const p = getAccessPolicy('expired');
    expect(p.mode).toBe('restricted');
    expect(p.reason).toBe('expired');
    expect(p.upgradePath).toBe('/upgrade/expired');
  });

  it.each<MembershipState | null | undefined>([
    'no_link',
    'verified',
    'pending_confirm',
    null,
    undefined,
  ])('%s → full access', (state) => {
    const p = getAccessPolicy(state);
    expect(p.mode).toBe('full');
    expect(p.reason).toBeNull();
  });
});

describe('isRouteAllowed', () => {
  const restricted = getAccessPolicy('frozen');
  const full = getAccessPolicy('verified');

  it('full access allows any route', () => {
    for (const path of ['/play', '/coach', '/database', '/anything']) {
      expect(isRouteAllowed(full, path)).toBe(true);
    }
  });

  it('restricted allows home, learn, settings, profile, upgrade', () => {
    for (const path of [
      '/dashboard',
      '/learn',
      '/settings',
      '/profile',
      '/upgrade',
    ]) {
      expect(isRouteAllowed(restricted, path)).toBe(true);
    }
  });

  it('restricted allows nested allowed routes (prefix match)', () => {
    expect(isRouteAllowed(restricted, '/learn/openings/italian')).toBe(true);
    expect(isRouteAllowed(restricted, '/upgrade/expired')).toBe(true);
  });

  it('restricted allows the root path (renders home)', () => {
    expect(isRouteAllowed(restricted, '/')).toBe(true);
  });

  it('restricted blocks locked features', () => {
    for (const path of Object.keys(LOCKED_FEATURES)) {
      expect(isRouteAllowed(restricted, path)).toBe(false);
    }
    expect(isRouteAllowed(restricted, '/games/wheel')).toBe(false);
  });

  it('does not allow a route that merely shares a name prefix', () => {
    // `/learning` must NOT be treated as under `/learn`.
    expect(isRouteAllowed(restricted, '/learning')).toBe(false);
  });
});

describe('featureKeyForPath', () => {
  it('maps locked routes to their feature key', () => {
    expect(featureKeyForPath('/play')).toBe('play');
    expect(featureKeyForPath('/coach')).toBe('coach');
    expect(featureKeyForPath('/database')).toBe('database');
    expect(featureKeyForPath('/puzzle')).toBe('puzzles');
    expect(featureKeyForPath('/games')).toBe('games');
    expect(featureKeyForPath('/editor')).toBe('editor');
  });

  it('matches nested locked routes', () => {
    expect(featureKeyForPath('/games/tug-of-war')).toBe('games');
  });

  it('returns null for allowed / unknown routes', () => {
    expect(featureKeyForPath('/learn')).toBeNull();
    expect(featureKeyForPath('/dashboard')).toBeNull();
  });
});
