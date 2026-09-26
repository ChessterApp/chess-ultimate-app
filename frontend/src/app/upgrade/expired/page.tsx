import { auth } from '@clerk/nextjs/server';
import { redirect } from 'next/navigation';
import UpgradeContent from '@/components/access/UpgradeContent';

export const dynamic = 'force-dynamic';

export default async function UpgradeExpiredPage() {
  const { userId } = await auth();
  if (!userId) redirect('/sign-in?redirect_url=/upgrade/expired');
  return <UpgradeContent audience="expired" />;
}
