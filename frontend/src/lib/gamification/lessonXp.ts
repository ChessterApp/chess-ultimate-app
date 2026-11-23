/**
 * XP a completed lesson is worth: by lesson type, growing with the course level.
 * One table (lessonXp.json) for the "+N XP" label, the XP animation and — via
 * the backend copy in `backend/api/lesson_xp.py`, kept equal by a backend test —
 * the server-side XP total.
 */
import LESSON_XP_TABLE from './lessonXp.json';

export const LESSON_XP: Record<string, { theory: number; exercise: number }> = LESSON_XP_TABLE;

/** Unknown level → beginner; unknown type → theory. */
export function lessonXp(lessonType: string | null | undefined, courseLevel: string | null | undefined): number {
  const row = courseLevel && Object.hasOwn(LESSON_XP, courseLevel) ? LESSON_XP[courseLevel] : LESSON_XP.beginner;
  return lessonType === 'exercise' ? row.exercise : row.theory;
}
