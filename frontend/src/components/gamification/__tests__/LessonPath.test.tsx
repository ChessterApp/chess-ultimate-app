/**
 * @vitest-environment jsdom
 */
import { describe, it, expect, vi } from 'vitest'
import React from 'react'
import { render, screen } from '@testing-library/react'
import { LessonPath, HorizontalLessonPath } from '../LessonPath'

// Mock next/link
vi.mock('next/link', () => ({
  default: ({ children, href, ...props }: { children: React.ReactNode; href: string; [key: string]: unknown }) => (
    <a href={href} {...props}>{children}</a>
  ),
}))

const makeCourse = (overrides: Partial<{
  id: string; slug: string; title: string;
  level: 'beginner' | 'intermediate' | 'advanced' | 'master' | 'expert' | 'legendary' | 'grandmaster';
  progress: number; isLocked: boolean;
}> = {}) => ({
  id: overrides.id ?? '1',
  slug: overrides.slug ?? 'basics',
  title: overrides.title ?? 'Chess Basics',
  level: overrides.level ?? 'beginner',
  progress: overrides.progress ?? 0,
  isLocked: overrides.isLocked ?? false,
  lessons: [],
})

describe('LessonPath', () => {
  it('renders course nodes for each course', () => {
    const courses = [
      makeCourse({ id: '1', title: 'Chess Basics', level: 'beginner' }),
      makeCourse({ id: '2', title: 'Tactics 101', level: 'beginner', slug: 'tactics-101' }),
    ]
    render(<LessonPath courses={courses} />)
    expect(screen.getByText('Chess Basics')).toBeTruthy()
    expect(screen.getByText('Tactics 101')).toBeTruthy()
  })

  it('renders section dividers with level labels', () => {
    const courses = [
      makeCourse({ id: '1', level: 'beginner' }),
      makeCourse({ id: '2', level: 'intermediate', slug: 'int-1', title: 'Int Course' }),
    ]
    const { container } = render(<LessonPath courses={courses} />)
    // Both level section dividers should be present
    expect(container.textContent).toContain('Level 1')
    expect(container.textContent).toContain('Level 2')
  })

  it('renders level icons for different levels', () => {
    const courses = [
      makeCourse({ id: '1', level: 'beginner', title: 'Beginner' }),
      makeCourse({ id: '2', level: 'advanced', title: 'Advanced', slug: 'adv' }),
    ]
    const { container } = render(<LessonPath courses={courses} />)
    // Pawn icon for beginner section, bishop for advanced
    expect(container.textContent).toContain('♟')
    expect(container.textContent).toContain('♝')
  })

  it('renders locked courses with lock icon and no link', () => {
    const courses = [
      makeCourse({ id: '1', isLocked: true, title: 'Locked Course' }),
    ]
    render(<LessonPath courses={courses} />)
    expect(screen.getByText('🔒')).toBeTruthy()
    // Link should point to # for locked courses
    const link = screen.getByLabelText('Locked Course')
    expect(link.getAttribute('href')).toBe('#')
  })

  it('renders completed courses with crown icon', () => {
    const courses = [
      makeCourse({ id: '1', progress: 100, title: 'Done Course' }),
    ]
    render(<LessonPath courses={courses} />)
    expect(screen.getByText('👑')).toBeTruthy()
  })

  it('renders active course with START button when progress is 0', () => {
    const courses = [
      makeCourse({ id: '1', progress: 0, title: 'New Course' }),
    ]
    render(<LessonPath courses={courses} />)
    expect(screen.getByText('START')).toBeTruthy()
  })

  it('renders active course with CONTINUE button when progress > 0', () => {
    const courses = [
      makeCourse({ id: '1', progress: 30, title: 'In Progress' }),
    ]
    render(<LessonPath courses={courses} />)
    expect(screen.getByText('CONTINUE')).toBeTruthy()
  })

  it('links active courses to /learn/{slug}', () => {
    const courses = [
      makeCourse({ id: '1', slug: 'basics', progress: 30 }),
    ]
    render(<LessonPath courses={courses} />)
    const link = screen.getByLabelText('Chess Basics')
    expect(link.getAttribute('href')).toBe('/learn/basics')
  })

  it('renders SVG curved connectors between nodes', () => {
    const courses = [
      makeCourse({ id: '1', title: 'First' }),
      makeCourse({ id: '2', title: 'Second', slug: 'second' }),
    ]
    const { container } = render(<LessonPath courses={courses} />)
    const svgs = container.querySelectorAll('svg[aria-hidden="true"]')
    // One connector between 2 nodes
    expect(svgs.length).toBe(1)
    const path = svgs[0].querySelector('path')
    expect(path).toBeTruthy()
    // Path should be a curve (contains C for cubic bezier)
    expect(path?.getAttribute('d')).toContain('C')
  })

  it('applies zigzag offset to nodes', () => {
    const courses = [
      makeCourse({ id: '1', title: 'First' }),
      makeCourse({ id: '2', title: 'Second', slug: 'second' }),
      makeCourse({ id: '3', title: 'Third', slug: 'third' }),
    ]
    const { container } = render(<LessonPath courses={courses} />)
    // Check that translate-x classes are applied alternately
    const nodes = container.querySelectorAll('.translate-x-10, .-translate-x-10')
    expect(nodes.length).toBe(3)
  })

  it('does not render START/CONTINUE for non-current courses', () => {
    const courses = [
      makeCourse({ id: '1', progress: 0, title: 'First' }),
      makeCourse({ id: '2', progress: 0, title: 'Second', slug: 'second' }),
    ]
    render(<LessonPath courses={courses} />)
    // Only the first unlocked course should have a button
    const buttons = screen.getAllByText(/^(START|CONTINUE)$/)
    expect(buttons.length).toBe(1)
  })
})

describe('HorizontalLessonPath', () => {
  const makeLesson = (overrides: Partial<{
    id: string; slug: string; title: string;
    isCompleted: boolean; isLocked: boolean; isCurrent: boolean;
  }> = {}) => ({
    id: overrides.id ?? '1',
    slug: overrides.slug ?? 'lesson-1',
    title: overrides.title ?? 'Lesson 1',
    isCompleted: overrides.isCompleted ?? false,
    isLocked: overrides.isLocked ?? false,
    isCurrent: overrides.isCurrent ?? false,
  })

  it('renders lesson nodes', () => {
    const lessons = [
      makeLesson({ id: '1', title: 'First Lesson' }),
      makeLesson({ id: '2', title: 'Second Lesson', slug: 'lesson-2' }),
    ]
    render(<HorizontalLessonPath lessons={lessons} courseSlug="basics" level="beginner" />)
    // Should render node numbers for non-completed, non-locked lessons
    expect(screen.getByText('1')).toBeTruthy()
    expect(screen.getByText('2')).toBeTruthy()
  })

  it('renders completed lessons with checkmark', () => {
    const lessons = [
      makeLesson({ id: '1', isCompleted: true }),
    ]
    render(<HorizontalLessonPath lessons={lessons} courseSlug="basics" level="beginner" />)
    expect(screen.getByText('✓')).toBeTruthy()
  })

  it('renders locked lessons with lock icon', () => {
    const lessons = [
      makeLesson({ id: '1', isLocked: true }),
    ]
    render(<HorizontalLessonPath lessons={lessons} courseSlug="basics" level="beginner" />)
    expect(screen.getByText('🔒')).toBeTruthy()
  })

  it('links lessons to correct URL', () => {
    const lessons = [
      makeLesson({ id: '1', slug: 'my-lesson' }),
    ]
    const { container } = render(<HorizontalLessonPath lessons={lessons} courseSlug="basics" level="beginner" />)
    const link = container.querySelector('a[href="/learn/basics/my-lesson"]')
    expect(link).toBeTruthy()
  })
})
