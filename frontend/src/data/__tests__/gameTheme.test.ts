/**
 * @vitest-environment node
 *
 * gameTheme resolves the V3 in-game screen theme: the tier world gradient dips
 * the whole screen while accent colors come from a beginner hero's personal
 * palette or the tier frame for everyone else.
 */
import { describe, it, expect } from 'vitest';

import { BOTS, TIER_WORLDS, gameTheme, getBotById } from '../bots';
import type { BotTier } from '../bots';

describe('gameTheme', () => {
  it('uses a beginner hero personal palette for accents but the tier gradient for the screen', () => {
    const luna = getBotById('luna-1100');
    expect(luna?.colors).toBeDefined();
    const theme = gameTheme(luna!);

    expect(theme.main).toBe(luna!.colors!.main);
    expect(theme.deep).toBe(luna!.colors!.deep);
    expect(theme.tint).toBe(luna!.colors!.tint);
    // Screen still uses the beginner world gradient, not a per-bot gradient.
    expect(theme.screenGradient).toBe(TIER_WORLDS.beginner.screenGradient);
    expect(theme.deco).toEqual(TIER_WORLDS.beginner.deco);
  });

  it('falls back to the tier frame palette for bots without personal colors', () => {
    const sven = getBotById('sven-1400'); // intermediate, no personal colors
    expect(sven?.colors).toBeUndefined();
    const theme = gameTheme(sven!);
    const frame = TIER_WORLDS.intermediate.frame;

    expect(theme.main).toBe(frame.main);
    expect(theme.deep).toBe(frame.deep);
    expect(theme.tint).toBe(frame.tint);
    expect(theme.screenGradient).toBe(TIER_WORLDS.intermediate.screenGradient);
  });

  it('gives every bot a screen gradient, world emoji and exactly three deco emojis', () => {
    for (const bot of BOTS) {
      const theme = gameTheme(bot);
      const world = TIER_WORLDS[bot.tier as BotTier];
      expect(theme.screenGradient).toBe(world.screenGradient);
      expect(theme.worldEmoji).toBe(world.emoji);
      expect(theme.worldKey).toBe(world.key);
      expect(theme.deco).toHaveLength(3);
      expect(theme.deco.every((e) => typeof e === 'string' && e.length > 0)).toBe(true);
    }
  });
});
