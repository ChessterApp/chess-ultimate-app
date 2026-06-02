// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { ANALYTICS_EVENTS, track } from '../events';

describe('ANALYTICS_EVENTS', () => {
  it('exposes wizard events with snake_case names', () => {
    expect(ANALYTICS_EVENTS.SCHOOL_ONBOARDING_STARTED).toBe('school_onboarding_started');
    expect(ANALYTICS_EVENTS.SCHOOL_ONBOARDING_PLAN_SELECTED).toBe('school_onboarding_plan_selected');
    expect(ANALYTICS_EVENTS.SCHOOL_ONBOARDING_CSV_IMPORTED).toBe('school_onboarding_csv_imported');
  });

  it('exposes checklist events', () => {
    expect(ANALYTICS_EVENTS.ONBOARDING_CHECKLIST_VIEWED).toBe('onboarding_checklist_viewed');
    expect(ANALYTICS_EVENTS.ONBOARDING_CHECKLIST_COMPLETED).toBe('onboarding_checklist_completed');
  });

  it('has no duplicate event values', () => {
    const values = Object.values(ANALYTICS_EVENTS);
    expect(new Set(values).size).toBe(values.length);
  });

  it('every event name is a non-empty snake_case string', () => {
    for (const v of Object.values(ANALYTICS_EVENTS)) {
      expect(typeof v).toBe('string');
      expect(v.length).toBeGreaterThan(0);
      expect(v).toMatch(/^[a-z][a-z0-9_]*$/);
    }
  });
});

describe('track()', () => {
  beforeEach(() => {
    // Reset any prior posthog mock.
    (window as unknown as { posthog?: unknown }).posthog = undefined;
  });

  afterEach(() => {
    (window as unknown as { posthog?: unknown }).posthog = undefined;
  });

  it('is a no-op when PostHog is not loaded', () => {
    // Should not throw.
    expect(() => track(ANALYTICS_EVENTS.SCHOOL_ONBOARDING_STARTED)).not.toThrow();
  });

  it('forwards to window.posthog.capture when present', () => {
    const capture = vi.fn();
    (window as unknown as { posthog: unknown }).posthog = { capture };
    track(ANALYTICS_EVENTS.SCHOOL_ONBOARDING_STARTED, { foo: 1 });
    expect(capture).toHaveBeenCalledWith('school_onboarding_started', { foo: 1 });
  });

  it('swallows errors from posthog.capture', () => {
    (window as unknown as { posthog: unknown }).posthog = {
      capture: () => {
        throw new Error('boom');
      },
    };
    expect(() => track(ANALYTICS_EVENTS.SCHOOL_ONBOARDING_STARTED)).not.toThrow();
  });
});
