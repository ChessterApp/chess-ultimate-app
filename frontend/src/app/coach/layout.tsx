import type { Viewport } from 'next';
import { requireAccess } from '@/lib/require-access';

// The root layout's viewport (segments do not merge it) plus
// interactive-widget: the on-screen keyboard shrinks 100dvh where supported,
// so the coach shell keeps its board and composer above the keyboard.
export const viewport: Viewport = {
  width: 'device-width',
  initialScale: 1,
  viewportFit: 'cover',
  interactiveWidget: 'resizes-content',
};

export default async function CoachLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  await requireAccess('/coach');
  return (
    // Phones: the page is a fixed full-screen shell (CoachShell); desktops get
    // the split layout at full height.
    // coach-theme: the page's colour variables (--coach-*, app/globals.css).
    <div className="coach-theme md:min-h-screen bg-(--coach-bg)">
      {children}
    </div>
  );
}
