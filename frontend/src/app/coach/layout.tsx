import { requireAccess } from '@/lib/require-access';

export default async function CoachLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  await requireAccess('/coach');
  return (
    // Phones: the page sizes itself between the app bars (see coach/page.tsx);
    // a full-screen minimum here would push it past them again.
    // coach-theme: the page's colour variables (--coach-*, app/globals.css).
    <div className="coach-theme md:min-h-screen bg-(--coach-bg)">
      {children}
    </div>
  );
}
