import { requireAccess } from '@/lib/require-access';

export default async function PlayLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  await requireAccess('/play');
  return <>{children}</>;
}
