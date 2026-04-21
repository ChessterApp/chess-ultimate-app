'use client';

import Link from 'next/link';
import { useTranslations } from 'next-intl';

interface Lesson {
  id: string;
  slug: string;
  title: string;
  isCompleted: boolean;
  isLocked: boolean;
  isCurrent: boolean;
}

interface Course {
  id: string;
  slug: string;
  title: string;
  level: 'beginner' | 'intermediate' | 'advanced' | 'master' | 'expert' | 'legendary' | 'grandmaster';
  progress: number;
  lessons: Lesson[];
  isLocked: boolean;
}

interface LessonPathProps {
  courses: Course[];
  courseSlug?: string;
}

const levelColors: Record<string, { bg: string; border: string; text: string; light: string; glow: string; gradient: string }> = {
  beginner: {
    bg: 'bg-green-500',
    border: 'border-green-500',
    text: 'text-green-600',
    light: 'bg-green-100',
    glow: 'shadow-green-400/50',
    gradient: 'from-green-400 to-green-600',
  },
  intermediate: {
    bg: 'bg-amber-500',
    border: 'border-amber-500',
    text: 'text-amber-600',
    light: 'bg-amber-100',
    glow: 'shadow-amber-400/50',
    gradient: 'from-amber-400 to-amber-600',
  },
  advanced: {
    bg: 'bg-red-500',
    border: 'border-red-500',
    text: 'text-red-600',
    light: 'bg-red-100',
    glow: 'shadow-red-400/50',
    gradient: 'from-red-400 to-red-600',
  },
  master: {
    bg: 'bg-purple-500',
    border: 'border-purple-500',
    text: 'text-purple-600',
    light: 'bg-purple-100',
    glow: 'shadow-purple-400/50',
    gradient: 'from-purple-400 to-purple-600',
  },
  expert: {
    bg: 'bg-amber-500',
    border: 'border-amber-500',
    text: 'text-amber-600',
    light: 'bg-amber-100',
    glow: 'shadow-amber-400/50',
    gradient: 'from-amber-400 to-amber-600',
  },
  legendary: {
    bg: 'bg-rose-500',
    border: 'border-rose-500',
    text: 'text-rose-600',
    light: 'bg-rose-100',
    glow: 'shadow-rose-400/50',
    gradient: 'from-rose-400 to-rose-600',
  },
  grandmaster: {
    bg: 'bg-indigo-500',
    border: 'border-indigo-500',
    text: 'text-indigo-600',
    light: 'bg-indigo-100',
    glow: 'shadow-indigo-400/50',
    gradient: 'from-indigo-400 to-indigo-600',
  },
};

const levelIcons: Record<string, string> = {
  beginner: '♟',
  intermediate: '♞',
  advanced: '♝',
  master: '♜',
  expert: '♛',
  legendary: '♚',
  grandmaster: '👑',
};

const levelKeys = ['beginner', 'intermediate', 'advanced', 'master', 'expert', 'legendary', 'grandmaster'] as const;

// Group courses by level for section dividers
function groupByLevel(courses: Course[]): { level: string; courses: Course[] }[] {
  const groups: { level: string; courses: Course[] }[] = [];
  let currentLevel = '';

  for (const course of courses) {
    if (course.level !== currentLevel) {
      currentLevel = course.level;
      groups.push({ level: currentLevel, courses: [course] });
    } else {
      groups[groups.length - 1].courses.push(course);
    }
  }

  return groups;
}

// Get zigzag X offset for a node at a given global index
function getZigzagOffset(index: number): string {
  // Odd nodes go left, even nodes go right (Duolingo-style)
  if (index % 2 === 0) return 'translate-x-10';
  return '-translate-x-10';
}

export function LessonPath({ courses, courseSlug }: LessonPathProps) {
  const t = useTranslations('learn');
  const groups = groupByLevel(courses);
  let globalIndex = 0;

  return (
    <div className="flex flex-col items-center py-6 relative">
      {groups.map((group, groupIndex) => (
        <div key={group.level} className="flex flex-col items-center w-full">
          {/* Section divider */}
          <div className="flex items-center gap-3 w-full max-w-xs mb-6 mt-2">
            <div className="flex-1 h-px bg-gray-200" />
            <span className={`text-xs font-bold uppercase tracking-wider ${levelColors[group.level]?.text || 'text-gray-500'}`}>
              {levelIcons[group.level]} {t(group.level as any)}
            </span>
            <div className="flex-1 h-px bg-gray-200" />
          </div>

          {group.courses.map((course, courseIndexInGroup) => {
            const nodeIndex = globalIndex++;
            const isCurrent = !course.isLocked && course.progress > 0 && course.progress < 100;
            const isNext = !course.isLocked && course.progress === 0;
            const isActive = isCurrent || isNext;
            const isCompleted = course.progress === 100;
            const isFirst = nodeIndex === 0 && groupIndex === 0;

            // Find the first active (non-locked, non-completed) course
            const firstActiveCourse = courses.find(c => !c.isLocked && c.progress < 100);
            const isCurrentActive = firstActiveCourse?.id === course.id;

            return (
              <div key={course.id} className="flex flex-col items-center">
                {/* SVG curved connector to previous node */}
                {!(isFirst && courseIndexInGroup === 0) && (
                  <svg width="120" height="48" viewBox="0 0 120 48" className="my-1" aria-hidden="true">
                    <path
                      d={nodeIndex % 2 === 0
                        ? 'M 20 0 C 20 24, 100 24, 100 48'
                        : 'M 100 0 C 100 24, 20 24, 20 48'
                      }
                      fill="none"
                      stroke={isCompleted || isActive ? '#a78bfa' : '#d1d5db'}
                      strokeWidth="3"
                      strokeLinecap="round"
                      strokeDasharray={isActive ? '6 4' : 'none'}
                    />
                  </svg>
                )}

                {/* Course node with zigzag offset */}
                <div className={`flex flex-col items-center transition-transform ${getZigzagOffset(nodeIndex)}`}>
                  <CourseNode
                    course={course}
                    isExpanded={course.slug === courseSlug}
                    courseIndex={nodeIndex}
                    isCurrentActive={isCurrentActive}
                  />
                </div>
              </div>
            );
          })}
        </div>
      ))}
    </div>
  );
}

interface CourseNodeProps {
  course: Course;
  isExpanded: boolean;
  courseIndex: number;
  isCurrentActive: boolean;
}

function CourseNode({ course, isExpanded, courseIndex, isCurrentActive }: CourseNodeProps) {
  const colors = levelColors[course.level] || levelColors.beginner;
  const isCompleted = course.progress === 100;
  const icon = levelIcons[course.level] || '♟';

  return (
    <div className="flex flex-col items-center">
      <Link
        href={course.isLocked ? '#' : `/learn/${course.slug}`}
        className={`relative flex items-center justify-center w-20 h-20 rounded-full transition-all duration-300 ${
          course.isLocked
            ? 'bg-gray-200 cursor-not-allowed border-4 border-gray-300'
            : isCompleted
            ? `bg-gradient-to-br ${colors.gradient} border-4 border-white shadow-lg`
            : isCurrentActive
            ? `${colors.light} border-4 ${colors.border} shadow-lg ${colors.glow} animate-pulse`
            : `bg-white border-4 ${colors.border} hover:scale-105 active:scale-95 shadow-md`
        }`}
        aria-label={course.title}
        onClick={course.isLocked ? (e: React.MouseEvent) => e.preventDefault() : undefined}
      >
        {/* Progress ring for non-locked, non-completed courses */}
        {!course.isLocked && !isCompleted && course.progress > 0 && (
          <svg className="absolute inset-0 w-full h-full -rotate-90" viewBox="0 0 80 80">
            <circle
              cx="40"
              cy="40"
              r="36"
              fill="none"
              stroke="currentColor"
              strokeWidth="4"
              className="text-gray-200"
            />
            <circle
              cx="40"
              cy="40"
              r="36"
              fill="none"
              stroke="currentColor"
              strokeWidth="4"
              strokeDasharray={`${course.progress * 2.26} 226`}
              strokeLinecap="round"
              className={colors.text}
            />
          </svg>
        )}

        {/* Icon content */}
        {course.isLocked ? (
          <span className="text-2xl text-gray-400">🔒</span>
        ) : isCompleted ? (
          <span className="text-3xl">👑</span>
        ) : (
          <span className="text-3xl relative z-10">{icon}</span>
        )}
      </Link>

      {/* Course title */}
      <div className="mt-2 text-center max-w-[120px]">
        <div className={`text-sm font-semibold ${course.isLocked ? 'text-gray-400' : 'text-gray-800'}`}>
          {course.title}
        </div>
      </div>

      {/* START / CONTINUE button for current active course */}
      {isCurrentActive && !course.isLocked && (
        <Link
          href={`/learn/${course.slug}`}
          className={`mt-2 px-5 py-1.5 rounded-full text-xs font-bold uppercase tracking-wide text-white bg-gradient-to-r ${colors.gradient} shadow-md hover:shadow-lg hover:scale-105 active:scale-95 transition-all`}
        >
          {course.progress > 0 ? 'CONTINUE' : 'START'}
        </Link>
      )}

      {/* Expanded lessons view */}
      {isExpanded && !course.isLocked && course.lessons.length > 0 && (
        <div className="mt-4 flex flex-col items-center">
          <div className="w-0.5 h-4 bg-gray-300" />
          {course.lessons.map((lesson, index) => (
            <div key={lesson.id} className="flex flex-col items-center">
              <LessonNode lesson={lesson} courseSlug={course.slug} colors={colors} />
              {index < course.lessons.length - 1 && (
                <div className="w-0.5 h-4 bg-gray-300" />
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

interface LessonNodeProps {
  lesson: Lesson;
  courseSlug: string;
  colors: typeof levelColors.beginner;
}

function LessonNode({ lesson, courseSlug, colors }: LessonNodeProps) {
  const nodeContent = (
    <div
      className={`w-14 h-14 rounded-xl flex items-center justify-center shadow-md transition-all duration-200 ${
        lesson.isLocked
          ? 'bg-gray-200 cursor-not-allowed'
          : lesson.isCompleted
          ? `${colors.bg} text-white`
          : lesson.isCurrent
          ? `${colors.light} ${colors.border} border-2 animate-pulse`
          : `bg-white ${colors.border} border-2`
      } ${!lesson.isLocked && 'hover:scale-105 active:scale-95'}`}
    >
      {lesson.isLocked ? (
        <span className="text-gray-400">🔒</span>
      ) : lesson.isCompleted ? (
        <span className="text-xl">✓</span>
      ) : (
        <span className={`text-xl ${colors.text}`}>♟</span>
      )}
    </div>
  );

  return (
    <div className="flex flex-col items-center">
      {lesson.isLocked ? (
        nodeContent
      ) : (
        <Link href={`/learn/${courseSlug}/${lesson.slug}`}>{nodeContent}</Link>
      )}
      <span
        className={`mt-1 text-xs text-center max-w-[80px] truncate ${
          lesson.isLocked ? 'text-gray-400' : 'text-gray-600'
        }`}
      >
        {lesson.title}
      </span>
    </div>
  );
}

// Simpler horizontal path for course overview
interface HorizontalLessonPathProps {
  lessons: Lesson[];
  courseSlug: string;
  level: 'beginner' | 'intermediate' | 'advanced' | 'master' | 'expert' | 'legendary' | 'grandmaster';
}

export function HorizontalLessonPath({ lessons, courseSlug, level }: HorizontalLessonPathProps) {
  const colors = levelColors[level] || levelColors.beginner;

  return (
    <div className="flex items-center gap-2 overflow-x-auto pb-2 px-4 -mx-4">
      {lessons.map((lesson, index) => (
        <div key={lesson.id} className="flex items-center shrink-0">
          <Link
            href={lesson.isLocked ? '#' : `/learn/${courseSlug}/${lesson.slug}`}
            className={`w-10 h-10 rounded-full flex items-center justify-center text-sm font-medium transition-all ${
              lesson.isLocked
                ? 'bg-gray-200 text-gray-400 cursor-not-allowed'
                : lesson.isCompleted
                ? `${colors.bg} text-white`
                : lesson.isCurrent
                ? `${colors.light} ${colors.text} ring-2 ring-offset-2 ${colors.border.replace('border', 'ring')}`
                : `bg-white border-2 ${colors.border} ${colors.text}`
            }`}
          >
            {lesson.isLocked ? '🔒' : lesson.isCompleted ? '✓' : index + 1}
          </Link>
          {index < lessons.length - 1 && (
            <div
              className={`w-4 h-0.5 ${
                lesson.isCompleted ? colors.bg : 'bg-gray-300'
              }`}
            />
          )}
        </div>
      ))}
    </div>
  );
}
