// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { ANALYTICS_EVENTS, PII_DENYLIST, setPersonProperties, stripPii, track } from '../events';

const { capture, identify } = vi.hoisted(() => ({ capture: vi.fn(), identify: vi.fn() }));
vi.mock('posthog-js', () => ({ default: { capture, identify } }));

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

  it('registers every companion event (spec §13)', () => {
    const COMPANION = [
      'egg_received',
      'competency_attempted',
      'competency_passed',
      'hatch_eligible',
      'companion_hatched',
      'companion_named',
      'quest_started',
      'quest_completed',
      'review_completed',
      'mastery_updated',
      'reward_granted',
      'weekly_goal_updated',
    ];
    const registered = new Set(Object.values(ANALYTICS_EVENTS));
    for (const e of COMPANION) {
      expect(registered.has(e), `companion event "${e}" must be registered`).toBe(true);
    }
  });
});

describe('stripPii()', () => {
  it('drops PII / raw-chess-text keys from tracked props', () => {
    const scrubbed = stripPii({
      name: 'Rufus',
      fen: '4k3/8/8/8/8/8/8/4K3 w - - 0 1',
      uci: 'e2e4',
      solution: 'd1d5',
      prompt: 'Capture the rook',
      competency: 'H_ROOK',
      quest_id: 'watchtower',
      version: 1,
      cohort: 'chess-empire',
    });
    // Nothing on the denylist survives…
    for (const k of PII_DENYLIST) {
      expect(scrubbed).not.toHaveProperty(k);
    }
    // …but stable, non-identifying analytics keys are preserved.
    expect(scrubbed).toMatchObject({
      competency: 'H_ROOK',
      quest_id: 'watchtower',
      version: 1,
      cohort: 'chess-empire',
    });
  });

  it('drops the extended contact / DOB / free-text keys (tracking plan §3)', () => {
    const scrubbed = stripPii({
      email: 'kid@example.com',
      Phone: '+77001234567',
      dob: '2016-05-01',
      birthday: '2016-05-01',
      birth_date: '2016-05-01',
      transcript: 'hello coach',
      message: 'what is a fork?',
      content: 'free text',
      learner_profile_id: 'lp_1',
      learner_age_band: '6-8',
    });
    expect(scrubbed).toEqual({ learner_profile_id: 'lp_1', learner_age_band: '6-8' });
  });

  it('scrubs nested person props ($set / $set_once)', () => {
    expect(
      stripPii({ $set: { path: 'kids', email: 'x@y.z' }, $set_once: { birthdate: 'x', signup_date: 'd' } }),
    ).toEqual({ $set: { path: 'kids' }, $set_once: { signup_date: 'd' } });
  });

  it('passes undefined through untouched', () => {
    expect(stripPii(undefined)).toBeUndefined();
  });
});

describe('track()', () => {
  beforeEach(() => {
    capture.mockReset();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('calls posthog.capture with the event name and PII-stripped props', () => {
    track(ANALYTICS_EVENTS.COMPANION_NAMED, { foo: 1, companion_name: 'Foxy', FEN: 'x' });
    expect(capture).toHaveBeenCalledWith('companion_named', { foo: 1 });
  });

  it('passes undefined props through', () => {
    track(ANALYTICS_EVENTS.SCHOOL_ONBOARDING_STARTED);
    expect(capture).toHaveBeenCalledWith('school_onboarding_started', undefined);
  });

  it('is a no-op server-side', () => {
    vi.stubGlobal('window', undefined);
    track(ANALYTICS_EVENTS.SCHOOL_ONBOARDING_STARTED, { foo: 1 });
    expect(capture).not.toHaveBeenCalled();
  });

  it('swallows errors from posthog.capture', () => {
    capture.mockImplementation(() => {
      throw new Error('boom');
    });
    expect(() => track(ANALYTICS_EVENTS.SCHOOL_ONBOARDING_STARTED)).not.toThrow();
  });
});

describe('setPersonProperties()', () => {
  it('identifies with scrubbed $set props', () => {
    identify.mockReset();
    setPersonProperties('user_1', { skill_tier: 'beginner', email: 'x@y.z' });
    expect(identify).toHaveBeenCalledWith('user_1', { skill_tier: 'beginner' });
  });
});

describe('§4 registry', () => {
  it('registers the T1 activation-funnel events', () => {
    const registered = new Set<string>(Object.values(ANALYTICS_EVENTS));
    for (const e of [
      'user_signed_up', 'onboarding_started', 'onboarding_step_completed', 'onboarding_completed',
      'level_assigned', 'lesson_completed', 'game_review_completed',
      'voice_session_ended',
    ]) {
      expect(registered.has(e), e).toBe(true);
    }
  });
});
