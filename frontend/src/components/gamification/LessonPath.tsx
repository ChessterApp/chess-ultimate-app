'use client';

import Link from 'next/link';

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
  level: 'beginner' | 'intermediate' | 'advanced' | 'master' | 'expert';
  progress: number;
  lessons: Lesson[];
  isLocked: boolean;
}

interface LessonPathProps {
  courses: Course[];
  courseSlug?: string;
}

const levelColors = {
  beginner: {
    bg: 'bg-green-500',
    border: 'border-green-500',
    text: 'text-green-600',
    light: 'bg-green-100',
  },
  intermediate: {
    bg: 'bg-amber-500',
    border: 'border-amber-500',
    text: 'text-amber-600',
    light: 'bg-amber-100',
  },
  advanced: {
    bg: 'bg-red-500',
    border: 'border-red-500',
    text: 'text-red-600',
    light: 'bg-red-100',
  },
  master: {
    bg: 'bg-purple-500',
    border: 'border-purple-500',
    text: 'text-purple-600',
    light: 'bg-purple-100',
  },
  expert: {
    bg: 'bg-amber-500',
    border: 'border-amber-500',
    text: 'text-amber-600',
    light: 'bg-amber-100',
  },
};

export function LessonPath({ courses, courseSlug }: LessonPathProps) {
  return (
    <div className="flex flex-col items-center py-4">
      {courses.map((course, courseIndex) => (
        <div key={course.id} className="flex flex-col items-center">
          {/* Course Node */}
          <CourseNode course={course} isExpanded={course.slug === courseSlug} courseIndex={courseIndex} />

          {/* Connector to next course */}
          {courseIndex < courses.length - 1 && (
            <div className="w-1 h-8 bg-gray-300 my-2" />
          )}
        </div>
      ))}
    </div>
  );
}

interface CourseNodeProps {
  course: Course;
  isExpanded: boolean;
  courseIndex: number;
}

function CourseNode({ course, isExpanded, courseIndex }: CourseNodeProps) {
  const colors = levelColors[course.level];

  return (
    <div className="flex flex-col items-center">
      <Link
        href={course.isLocked ? '#' : `/learn/${course.slug}`}
        className={`relative flex flex-col items-center justify-center w-24 h-24 rounded-2xl shadow-lg transition-all duration-200 ${
          course.isLocked
            ? 'bg-gray-200 cursor-not-allowed'
            : `${colors.light} hover:scale-105 active:scale-95`
        }`}
      >
        {/* Lock overlay */}
        {course.isLocked && (
          <div className="absolute inset-0 flex items-center justify-center bg-gray-400/20 rounded-2xl">
            <span className="text-3xl">🔒</span>
          </div>
        )}

        {/* Progress ring */}
        {!course.isLocked && (
          <svg className="absolute inset-0 w-full h-full -rotate-90">
            <circle
              cx="48"
              cy="48"
              r="44"
              fill="none"
              stroke="currentColor"
              strokeWidth="4"
              className="text-gray-200"
            />
            <circle
              cx="48"
              cy="48"
              r="44"
              fill="none"
              stroke="currentColor"
              strokeWidth="4"
              strokeDasharray={`${course.progress * 2.76} 276`}
              className={colors.text}
            />
          </svg>
        )}

        {/* Course number and level indicator */}
        <div className={`relative z-10 text-2xl font-bold ${course.isLocked ? 'text-gray-400' : colors.text}`}>
          {course.progress === 100 ? '✓' : courseIndex + 1}
        </div>
      </Link>

      {/* Course title */}
      <div className="mt-2 text-center max-w-[120px]">
        <div className={`text-sm font-semibold ${course.isLocked ? 'text-gray-400' : 'text-gray-800'}`}>
          {course.title}
        </div>
        <div className={`text-xs ${colors.text} capitalize`}>{course.level}</div>
      </div>

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
  level: 'beginner' | 'intermediate' | 'advanced' | 'master' | 'expert';
}

export function HorizontalLessonPath({ lessons, courseSlug, level }: HorizontalLessonPathProps) {
  const colors = levelColors[level];

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
