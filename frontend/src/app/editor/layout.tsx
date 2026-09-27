import { requireAccess } from '@/lib/require-access';

export default async function EditorLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  await requireAccess('/editor');
  return <>{children}</>;
}
