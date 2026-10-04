/**
 * Unit tests for the onboarding tier derivation. Mirrors the Python test
 * `backend/tests/test_onboarding_tier.py` — the two derivations MUST agree on
 * every boundary (rating bands beat experience; slider default = 800).
 */
import { describe, it, expect } from "vitest";
import { deriveTier, DEFAULT_ELO_RATING } from "../onboarding/deriveTier";

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

  it("boundary 1399 -> advanced, 1400 -> elo_1400", () => {
    expect(deriveTier({ onlineRating: 1399 }).skillTier).toBe("advanced");
    expect(deriveTier({ onlineRating: 1400 }).skillTier).toBe("elo_1400");
  });

  it("1-1399 with a rating -> advanced / level 3 / mateIn2", () => {
    expect(deriveTier({ onlineRating: 1 })).toEqual({
      skillTier: "advanced",
      startingLevel: 3,
      puzzleTheme: "mateIn2",
    });
    expect(deriveTier({ onlineRating: 1399 }).skillTier).toBe("advanced");
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

  it("default slider (800) -> advanced when no online rating / no noRating", () => {
    expect(deriveTier({ experience: "beginner" }).skillTier).toBe("advanced");
    expect(deriveTier({ eloRating: DEFAULT_ELO_RATING }).skillTier).toBe("advanced");
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
  it("empty / null answers -> beginner (slider default pushes to advanced only without noRating)", () => {
    // No experience, no noRating => slider defaults to 800 => advanced.
    expect(deriveTier({}).skillTier).toBe("advanced");
    expect(deriveTier(null).skillTier).toBe("advanced");
    expect(deriveTier(undefined).skillTier).toBe("advanced");
  });

  it("startingLevel is never below 1", () => {
    for (const r of [0, 1, 800, 1400, 1600]) {
      expect(deriveTier({ onlineRating: r }).startingLevel).toBeGreaterThanOrEqual(1);
    }
  });
});
