/**
 * Onboarding skill-tier + starting-level derivation (single source of truth).
 *
 * Pure, framework-free. Mirror of the Python implementation at
 * `backend/services/onboarding_tier.py` — keep the bands/outputs IDENTICAL on
 * both sides (see the onboarding-persist spec). If you change a band here,
 * change it there too.
 *
 * Inputs (from the anonymous onboarding funnel, camelCase):
 *   experience    "beginner" | "intermediate" | "advanced"
 *   onlineRating  number, rating pulled from Chess.com/Lichess (0 if none)
 *   eloRating     number, self-rated slider (defaults to 800)
 *   noRating      bool, user checked "I don't have a rating"
 *
 * Effective rating:
 *   rating = onlineRating > 0 ? onlineRating : (noRating ? null : eloRating)
 *   i.e. a platform rating wins; otherwise the self-rated slider applies unless
 *   the user explicitly has no rating, in which case experience decides the tier.
 *
 * Derivation table (first match wins; rating bands beat experience):
 *   rating >= 1600                         -> elo_1600    level 6   mateIn3
 *   rating 1500-1599                       -> elo_1500    level 5   mateIn3
 *   rating 1400-1499                       -> elo_1400    level 4   mateIn3
 *   rating 1-1399 (has some rating)        -> advanced    level 3   mateIn2
 *   no rating, experience == advanced      -> advanced    level 3   mateIn2
 *   no rating, experience == intermediate  -> knows_rules level 2   mateIn1
 *   otherwise (beginner / unknown)         -> beginner    level 1   beginner
 *
 * startingLevel is clamped server-side to [1, numLevels] (never below 1). This
 * client mirror does NOT clamp (the funnel has no course count) — the backend
 * `/api/onboarding/profile` endpoint is the source of truth for the final value.
 */

// Default self-rated elo when the slider value is absent (see frontend default).
export const DEFAULT_ELO_RATING = 800;

export type SkillTier =
  | "elo_1600"
  | "elo_1500"
  | "elo_1400"
  | "advanced"
  | "knows_rules"
  | "beginner";

export type PuzzleTheme = "mateIn1" | "mateIn2" | "mateIn3" | "beginner";

// Puzzle theme per tier — kept here so the mapping is centralized and trivially
// adjustable. Mirrors PUZZLE_THEME_BY_TIER in onboarding_tier.py.
export const PUZZLE_THEME_BY_TIER: Record<SkillTier, PuzzleTheme> = {
  elo_1600: "mateIn3",
  elo_1500: "mateIn3",
  elo_1400: "mateIn3",
  advanced: "mateIn2",
  knows_rules: "mateIn1",
  beginner: "beginner",
};

export interface DeriveTierAnswers {
  experience?: string;
  onlineRating?: number;
  eloRating?: number;
  noRating?: boolean;
}

export interface DeriveTierResult {
  skillTier: SkillTier;
  startingLevel: number;
  puzzleTheme: PuzzleTheme;
}

function toInt(value: unknown): number {
  const n = typeof value === "number" ? value : parseInt(String(value), 10);
  return Number.isFinite(n) ? Math.trunc(n) : 0;
}

/**
 * Derive {skillTier, startingLevel, puzzleTheme} from onboarding answers.
 *
 * startingLevel is the UNCLAMPED tier level (1..6); the backend clamps it to
 * the real course count. puzzleTheme drives the StepPuzzle board selection.
 */
export function deriveTier(answers: DeriveTierAnswers | null | undefined): DeriveTierResult {
  const a = answers || {};

  const onlineRating = toInt(a.onlineRating);
  const noRating = Boolean(a.noRating);

  const eloRating = a.eloRating != null ? toInt(a.eloRating) : DEFAULT_ELO_RATING;

  const experience = String(a.experience ?? "").trim().toLowerCase();

  // Effective rating: platform rating wins; else slider unless "no rating".
  let rating: number | null;
  if (onlineRating > 0) {
    rating = onlineRating;
  } else if (noRating) {
    rating = null;
  } else {
    rating = eloRating;
  }

  let skillTier: SkillTier;
  let level: number;
  if (rating !== null && rating >= 1600) {
    skillTier = "elo_1600";
    level = 6;
  } else if (rating !== null && rating >= 1500 && rating <= 1599) {
    skillTier = "elo_1500";
    level = 5;
  } else if (rating !== null && rating >= 1400 && rating <= 1499) {
    skillTier = "elo_1400";
    level = 4;
  } else if (rating !== null && rating >= 1) {
    skillTier = "advanced";
    level = 3;
  } else if (experience === "advanced") {
    skillTier = "advanced";
    level = 3;
  } else if (experience === "intermediate") {
    skillTier = "knows_rules";
    level = 2;
  } else {
    skillTier = "beginner";
    level = 1;
  }

  return {
    skillTier,
    startingLevel: Math.max(1, level),
    puzzleTheme: PUZZLE_THEME_BY_TIER[skillTier],
  };
}
