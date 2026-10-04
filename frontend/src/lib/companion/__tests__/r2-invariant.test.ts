/**
 * @vitest-environment node
 *
 * R2 HARD INVARIANT (companion architecture plan, WP00 audit R2):
 *
 *   The weekly practice-days goal and the quests NEVER gate or unlock anything
 *   educational, and a missed week applies NO penalty.
 *
 * This test proves it three ways:
 *  1. The goal/quest rules expose NO gating/penalty surface (no "gate/block/
 *     unlock/penalty/lock" export; `met` is the only pass/fail-ish field and it
 *     is informational).
 *  2. A missed week is harmless: zero activity → progress 0, met false, target
 *     preserved, nothing negative — across many consecutive missed weeks.
 *  3. The educational code paths (assessment / review / watchtower / assignment
 *     / attempt / hint routes + services) do NOT import the goal or quest
 *     modules, so quest/goal state cannot possibly block learning.
 */
import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import * as goalRules from '../goal-rules';
import * as questRules from '../quest-rules';
import { computeGoalProgress } from '../goal-rules';
import { computeQuestState } from '../quest-rules';

const FORBIDDEN_EXPORT = /gate|block|unlock|penalt|deduct|forfeit|canaccess/i;

describe('R2 — goal & quest rules expose no gating/penalty surface', () => {
  it('no goal-rules export name implies gating or penalty', () => {
    for (const name of Object.keys(goalRules)) {
      expect(FORBIDDEN_EXPORT.test(name), `goal-rules.${name} looks like a gate`).toBe(false);
    }
  });
  it('no quest-rules export name implies gating or penalty', () => {
    for (const name of Object.keys(questRules)) {
      expect(FORBIDDEN_EXPORT.test(name), `quest-rules.${name} looks like a gate`).toBe(false);
    }
  });
});

describe('R2 — a missed week has no penalty', () => {
  it('zero-activity weeks never go negative and never change the target', () => {
    const DAY = 86_400_000;
    const target = 3;
    // Ten consecutive missed weeks — progress stays 0, met false, target intact.
    for (let w = 0; w < 10; w++) {
      const now = new Date(Date.UTC(2026, 0, 5) + w * 7 * DAY); // Mondays
      const r = computeGoalProgress({ target, activities: [], now });
      expect(r.target).toBe(target); // never decays
      expect(r.progress).toBe(0);
      expect(r.met).toBe(false);
      expect(r.progress).toBeGreaterThanOrEqual(0);
      // No penalty/blocked field leaks into the view.
      expect(Object.keys(r).sort()).toEqual(
        ['met', 'progress', 'target', 'week_end', 'week_start'].sort(),
      );
    }
  });

  it('earned history in a prior week is unaffected by a later empty week', () => {
    const DAY = 86_400_000;
    const act = [{ kind: 'learning', at: '2026-01-06T10:00:00.000Z' }];
    const inWeek = new Date('2026-01-07T10:00:00.000Z');
    const laterWeek = new Date(inWeek.getTime() + 21 * DAY);
    expect(computeGoalProgress({ target: 3, activities: act, now: inWeek }).progress).toBe(1);
    // A much later (empty) week doesn't retroactively erase or penalise it.
    expect(computeGoalProgress({ target: 3, activities: act, now: laterWeek }).progress).toBe(0);
  });
});

describe('R2 — quest state is observational, never a gate', () => {
  it('every quest state is reachable without affecting any educational flag', () => {
    const states = new Set(
      [
        { prerequisitesMet: false, started: false, done: 0, total: 6, alreadyCompleted: false },
        { prerequisitesMet: true, started: false, done: 0, total: 6, alreadyCompleted: false },
        { prerequisitesMet: true, started: true, done: 1, total: 6, alreadyCompleted: false },
        { prerequisitesMet: true, started: true, done: 6, total: 6, alreadyCompleted: false },
        { prerequisitesMet: true, started: true, done: 6, total: 6, alreadyCompleted: true },
      ].map(computeQuestState),
    );
    // All five states exist and are pure strings — no behavioral coupling.
    expect(states).toEqual(
      new Set(['locked', 'available', 'active', 'objectives_complete', 'completed']),
    );
  });
});

describe('R2 — educational paths never import goal/quest modules', () => {
  const here = resolve(__dirname, '..');
  const apiRoot = resolve(here, '../../app/api/gamification/companion');
  const EDUCATIONAL_SOURCES = [
    resolve(here, 'assessment-service.ts'),
    resolve(here, 'review-service.ts'),
    resolve(here, 'watchtower-service.ts'),
    resolve(apiRoot, 'assignments/route.ts'),
    resolve(apiRoot, 'attempts/route.ts'),
    resolve(apiRoot, 'hints/route.ts'),
    resolve(apiRoot, 'reviews/route.ts'),
    resolve(apiRoot, 'reviews/due/route.ts'),
    resolve(apiRoot, 'watchtower/route.ts'),
  ];
  const GOAL_QUEST = /(goal-rules|goal-service|quest-rules|quest-service)/;

  it('no learning-path source references a goal or quest module', () => {
    for (const file of EDUCATIONAL_SOURCES) {
      const src = readFileSync(file, 'utf8');
      expect(GOAL_QUEST.test(src), `${file} must not depend on goal/quest`).toBe(false);
    }
  });
});
