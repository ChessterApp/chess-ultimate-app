/**
 * When the "Complete lesson" button is enabled. Pure so it can be unit tested.
 */

// A paragraph that is only a YouTube link is rendered as an embedded video.
export const YOUTUBE_URL_REGEX =
  /^https?:\/\/(?:www\.)?(?:youtube\.com\/(?:embed\/|watch\?v=)|youtu\.be\/)([a-zA-Z0-9_-]{11})(?:\?.*)?$/

/** True when the lesson's markdown embeds at least one YouTube video. */
export function lessonHasVideo(content: string | null | undefined): boolean {
  return (content ?? '').split(/\n\s*\n/).some((para) => YOUTUBE_URL_REGEX.test(para.trim()))
}

export interface CompletionGate {
  /** The server already has this lesson as completed. */
  alreadyCompleted: boolean
  /** An exercise lesson showing a board (single puzzle or a puzzle sequence). */
  hasExercise: boolean
  /** The exercise / every puzzle of the sequence is solved. */
  exerciseSolved: boolean
  hasVideo: boolean
  /** The video ended — or the player failed and the fallback delay passed. */
  videoDone: boolean
}

export function canCompleteLesson(g: CompletionGate): boolean {
  if (g.alreadyCompleted) return true
  if (g.hasExercise) return g.exerciseSolved
  if (g.hasVideo) return g.videoDone
  return true
}
