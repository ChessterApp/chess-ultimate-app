import { requireAccess } from '@/lib/require-access';

export default async function DatabaseLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  await requireAccess('/database');
  return <>{children}</>;
}
