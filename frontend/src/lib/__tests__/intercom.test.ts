import { describe, it, expect } from 'vitest';
import { buildBootSettings, isPayingTier } from '../intercom';

describe('isPayingTier', () => {
  it('returns true for growth/pro/enterprise', () => {
    expect(isPayingTier('growth')).toBe(true);
    expect(isPayingTier('pro')).toBe(true);
    expect(isPayingTier('enterprise')).toBe(true);
  });
  it('returns false for starter', () => {
    expect(isPayingTier('starter')).toBe(false);
  });
  it('returns false for null/undefined/unknown', () => {
    expect(isPayingTier(null)).toBe(false);
    expect(isPayingTier(undefined)).toBe(false);
    expect(isPayingTier('platinum')).toBe(false);
    expect(isPayingTier('')).toBe(false);
  });
});

describe('buildBootSettings', () => {
  it('returns null when appId missing', () => {
    expect(
      buildBootSettings({ appId: '', tier: 'growth' }),
    ).toBeNull();
    expect(
      buildBootSettings({ appId: null, tier: 'growth' }),
    ).toBeNull();
  });

  it('returns null for starter tier', () => {
    expect(
      buildBootSettings({ appId: 'app_x', tier: 'starter' }),
    ).toBeNull();
  });

  it('returns null when tier missing', () => {
    expect(
      buildBootSettings({ appId: 'app_x', tier: null }),
    ).toBeNull();
  });

  it('returns settings for growth tier', () => {
    const s = buildBootSettings({
      appId: 'app_x',
      tier: 'growth',
      userId: 'u1',
      email: 'a@b.com',
      name: 'Alex',
      orgId: 'org-1',
      orgName: 'Almaty',
    });
    expect(s).not.toBeNull();
    expect(s!.app_id).toBe('app_x');
    expect(s!.user_id).toBe('u1');
    expect(s!.email).toBe('a@b.com');
    expect(s!.name).toBe('Alex');
    expect(s!.company).toEqual({
      id: 'org-1',
      name: 'Almaty',
      plan: 'growth',
    });
  });

  it('omits company when orgId missing', () => {
    const s = buildBootSettings({
      appId: 'app_x',
      tier: 'pro',
      userId: 'u1',
    });
    expect(s).not.toBeNull();
    expect(s!.company).toBeUndefined();
  });

  it('includes only present fields', () => {
    const s = buildBootSettings({
      appId: 'app_x',
      tier: 'enterprise',
      orgId: 'org-1',
    });
    expect(s).not.toBeNull();
    expect(s!.app_id).toBe('app_x');
    expect(s!.user_id).toBeUndefined();
    expect(s!.email).toBeUndefined();
    expect(s!.name).toBeUndefined();
    expect(s!.company).toEqual({ id: 'org-1', plan: 'enterprise' });
  });

  it('enterprise without orgName still works', () => {
    const s = buildBootSettings({
      appId: 'app_x',
      tier: 'enterprise',
      orgId: 'org-1',
      orgName: null,
    });
    expect(s!.company).toEqual({ id: 'org-1', plan: 'enterprise' });
  });
});
