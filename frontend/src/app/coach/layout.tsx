import { requireAccess } from '@/lib/require-access';

export default async function CoachLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  await requireAccess('/coach');
  return (
    <div className="min-h-screen" style={{ background: '#1a1a2e' }}>
      {children}
    </div>
  );
}
