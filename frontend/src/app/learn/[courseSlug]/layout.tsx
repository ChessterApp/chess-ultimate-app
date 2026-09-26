/**
 * Server-side ceiling guard for a restricted (frozen/expired) member. Covers
 * both the course overview (`[courseSlug]/page.tsx`) and every lesson beneath it
 * (`[courseSlug]/[lessonSlug]/page.tsx`). If the requested course sits ABOVE the
 * member's current-level ceiling, bounce back to `/learn?locked=level` where the
 * global `LockedRedirectListener` opens the contextual upgrade modal. Never
 * trust client state — the LessonPath lock is cosmetic; this is the real gate.
 *
 * Full-access members pass straight through with no backend round-trip.
 */
import { redirect } from 'next/navigation';
import { resolveLearnCeiling } from '@/lib/learn-ceiling-server';

export default async function CourseCeilingGuardLayout({
  children,
  params,
}: {
  children: React.ReactNode;
  params: Promise<{ courseSlug: string }>;
}) {
  const { courseSlug } = await params;
  const { policy, ceiling, courses } = await resolveLearnCeiling();

  if (policy.mode === 'restricted' && ceiling !== undefined) {
    const course = courses.find((c) => c.slug === courseSlug);
    // A completed course is always reachable (ownComplete invariant); only lock
    // an above-ceiling course the member has not finished.
    if (course && course.position > ceiling && course.progress < 100) {
      redirect('/learn?locked=level');
    }
  }

  return <>{children}</>;
}
