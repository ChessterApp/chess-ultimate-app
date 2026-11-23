import { describe, expect, it } from 'vitest';
import { canCompleteLesson, lessonHasVideo, type CompletionGate } from '../lesson-completion';

const base: CompletionGate = {
  alreadyCompleted: false,
  hasExercise: false,
  exerciseSolved: false,
  hasVideo: false,
  videoDone: false,
};

describe('canCompleteLesson — when "Complete lesson" is enabled', () => {
  it('plain theory lesson: always enabled', () => {
    expect(canCompleteLesson(base)).toBe(true);
  });

  it('exercise: only once solved', () => {
    expect(canCompleteLesson({ ...base, hasExercise: true })).toBe(false);
    expect(canCompleteLesson({ ...base, hasExercise: true, exerciseSolved: true })).toBe(true);
  });

  it('exercise gating ignores any video in the lesson', () => {
    expect(canCompleteLesson({ ...base, hasExercise: true, hasVideo: true, videoDone: true })).toBe(false);
  });

  it('theory with a video: only once the video ended (or the fallback fired)', () => {
    expect(canCompleteLesson({ ...base, hasVideo: true })).toBe(false);
    expect(canCompleteLesson({ ...base, hasVideo: true, videoDone: true })).toBe(true);
  });

  it('an already completed lesson is always enabled', () => {
    expect(canCompleteLesson({ ...base, alreadyCompleted: true, hasExercise: true })).toBe(true);
    expect(canCompleteLesson({ ...base, alreadyCompleted: true, hasVideo: true })).toBe(true);
  });
});

describe('lessonHasVideo', () => {
  it('detects a paragraph that is only a YouTube link', () => {
    expect(lessonHasVideo('Intro\n\nhttps://www.youtube.com/watch?v=dQw4w9WgXcQ\n\nOutro')).toBe(true);
    expect(lessonHasVideo('https://youtu.be/dQw4w9WgXcQ')).toBe(true);
    expect(lessonHasVideo('  https://www.youtube.com/embed/dQw4w9WgXcQ  ')).toBe(true);
  });

  it('ignores inline links and lessons without video', () => {
    expect(lessonHasVideo('See https://www.youtube.com/watch?v=dQw4w9WgXcQ for more')).toBe(false);
    expect(lessonHasVideo('Just text')).toBe(false);
    expect(lessonHasVideo(null)).toBe(false);
  });
});
