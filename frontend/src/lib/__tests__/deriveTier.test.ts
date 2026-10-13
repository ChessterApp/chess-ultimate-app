/**
 * Unit tests for the onboarding tier derivation. Mirrors the Python test
 * `backend/tests/test_onboarding_tier.py` — the two derivations MUST agree on
 * every boundary (ratings >= 1400 beat experience; below 1400 experience
 * decides; slider default = 800).
 */
import { describe, it, expect } from "vitest";
import {
  deriveTier,
  DEFAULT_ELO_RATING,
  PUZZLE_THEME_BY_TIER,
  type SkillTier,
} from "../onboarding/deriveTier";

describe("deriveTier — rating bands", () => {
  it("1600+ -> elo_1600 / level 6 / mateIn3", () => {
    expect(deriveTier({ onlineRating: 1600 })).toEqual({
      skillTier: "elo_1600",
      startingLevel: 6,
      puzzleTheme: "mateIn3",
    });
    expect(deriveTier({ onlineRating: 2200 }).skillTier).toBe("elo_1600");
  });

  it("boundary 1599 -> elo_1500, 1600 -> elo_1600", () => {
    expect(deriveTier({ onlineRating: 1599 }).skillTier).toBe("elo_1500");
    expect(deriveTier({ onlineRating: 1600 }).skillTier).toBe("elo_1600");
  });

  it("1500-1599 -> elo_1500 / level 5 / mateIn3", () => {
    expect(deriveTier({ onlineRating: 1500 })).toEqual({
      skillTier: "elo_1500",
      startingLevel: 5,
      puzzleTheme: "mateIn3",
    });
  });

  it("boundary 1499 -> elo_1400, 1500 -> elo_1500", () => {
    expect(deriveTier({ onlineRating: 1499 }).skillTier).toBe("elo_1400");
    expect(deriveTier({ onlineRating: 1500 }).skillTier).toBe("elo_1500");
  });

  it("1400-1499 -> elo_1400 / level 4 / mateIn3", () => {
    expect(deriveTier({ onlineRating: 1400 })).toEqual({
      skillTier: "elo_1400",
      startingLevel: 4,
      puzzleTheme: "mateIn3",
    });
  });

  it("boundary 1399 -> experience decides, 1400 -> elo_1400", () => {
    expect(deriveTier({ onlineRating: 1399, experience: "beginner" })).toEqual({
      skillTier: "beginner",
      startingLevel: 1,
      puzzleTheme: "beginner",
    });
    expect(deriveTier({ onlineRating: 1400 }).skillTier).toBe("elo_1400");
  });

  it("ratings below 1400 never override experience", () => {
    expect(deriveTier({ onlineRating: 1, experience: "intermediate" })).toEqual({
      skillTier: "knows_rules",
      startingLevel: 2,
      puzzleTheme: "mateIn1",
    });
  });

  it("slider 1450 -> elo_1400 / level 4 regardless of experience", () => {
    for (const experience of ["beginner", "intermediate", "advanced", ""]) {
      expect(deriveTier({ eloRating: 1450, experience })).toEqual({
        skillTier: "elo_1400",
        startingLevel: 4,
        puzzleTheme: "mateIn3",
      });
    }
  });
});

describe("deriveTier — effective rating selection", () => {
  it("online rating wins over slider + experience", () => {
    expect(
      deriveTier({ onlineRating: 1600, eloRating: 400, experience: "beginner" }).skillTier,
    ).toBe("elo_1600");
  });

  it("slider applies when no online rating and noRating is false", () => {
    expect(deriveTier({ onlineRating: 0, eloRating: 1500, noRating: false }).skillTier).toBe(
      "elo_1500",
    );
  });

  it("default slider (800) defers to experience", () => {
    expect(deriveTier({ experience: "beginner" })).toMatchObject({
      skillTier: "beginner",
      startingLevel: 1,
    });
    expect(deriveTier({ experience: "intermediate" })).toMatchObject({
      skillTier: "knows_rules",
      startingLevel: 2,
    });
    expect(deriveTier({ experience: "advanced" })).toMatchObject({
      skillTier: "advanced",
      startingLevel: 3,
    });
    expect(deriveTier({ eloRating: DEFAULT_ELO_RATING }).skillTier).toBe("beginner");
  });
});

describe("deriveTier — no rating falls through to experience", () => {
  it("noRating + advanced -> advanced / level 3 / mateIn2", () => {
    expect(deriveTier({ noRating: true, experience: "advanced" })).toEqual({
      skillTier: "advanced",
      startingLevel: 3,
      puzzleTheme: "mateIn2",
    });
  });

  it("noRating + intermediate -> knows_rules / level 2 / mateIn1", () => {
    expect(deriveTier({ noRating: true, experience: "intermediate" })).toEqual({
      skillTier: "knows_rules",
      startingLevel: 2,
      puzzleTheme: "mateIn1",
    });
  });

  it("noRating + beginner -> beginner / level 1 / beginner", () => {
    expect(deriveTier({ noRating: true, experience: "beginner" })).toEqual({
      skillTier: "beginner",
      startingLevel: 1,
      puzzleTheme: "beginner",
    });
  });

  it("noRating + unknown experience -> beginner", () => {
    expect(deriveTier({ noRating: true }).skillTier).toBe("beginner");
    expect(deriveTier({ noRating: true, experience: "" }).skillTier).toBe("beginner");
  });

  it("noRating ignores the slider value entirely", () => {
    // eloRating high but noRating checked => experience decides, not the slider.
    expect(
      deriveTier({ noRating: true, eloRating: 2000, experience: "intermediate" }).skillTier,
    ).toBe("knows_rules");
  });
});

describe("deriveTier — robustness", () => {
  it("empty / null answers -> beginner", () => {
    // No experience, no noRating => slider defaults to 800 (< 1400) => beginner.
    expect(deriveTier({}).skillTier).toBe("beginner");
    expect(deriveTier(null).skillTier).toBe("beginner");
    expect(deriveTier(undefined).skillTier).toBe("beginner");
  });

  it("startingLevel is never below 1", () => {
    for (const r of [0, 1, 800, 1400, 1600]) {
      expect(deriveTier({ onlineRating: r }).startingLevel).toBeGreaterThanOrEqual(1);
    }
  });
});

// Shared mirror table — IDENTICAL to SHARED_CASES in
// backend/tests/test_onboarding_tier.py. If you edit one, edit the other so the
// Python/TS mirrors can't drift.
// [experience, onlineRating, eloRating, noRating] -> [skillTier, level]
const SHARED_CASES: [string, number, number | null, boolean, SkillTier, number][] = [
  ["beginner", 0, null, false, "beginner", 1],
  ["intermediate", 0, null, false, "knows_rules", 2],
  ["advanced", 0, null, false, "advanced", 3],
  ["beginner", 1399, null, false, "beginner", 1],
  ["intermediate", 1, null, false, "knows_rules", 2],
  ["beginner", 1400, null, false, "elo_1400", 4],
  ["beginner", 1500, null, false, "elo_1500", 5],
  ["beginner", 1600, null, false, "elo_1600", 6],
  ["beginner", 0, 1450, false, "elo_1400", 4],
  ["advanced", 0, 1450, false, "elo_1400", 4],
  ["advanced", 0, 1399, false, "advanced", 3],
  ["intermediate", 0, 2000, true, "knows_rules", 2],
  ["beginner", 1700, 200, true, "elo_1600", 6],
];

describe("deriveTier — shared mirror table", () => {
  it.each(SHARED_CASES)(
    "%s / online %i / slider %s / noRating %s -> %s level %i",
    (experience, onlineRating, eloRating, noRating, skillTier, level) => {
      const result = deriveTier({
        experience,
        onlineRating,
        noRating,
        ...(eloRating !== null ? { eloRating } : {}),
      });
      expect(result).toEqual({
        skillTier,
        startingLevel: level,
        puzzleTheme: PUZZLE_THEME_BY_TIER[skillTier],
      });
    },
  );
});
