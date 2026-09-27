import { requireAccess } from '@/lib/require-access';

export default async function GamesLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  await requireAccess('/games');
  return <>{children}</>;
}
