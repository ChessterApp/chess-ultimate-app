import { auth } from '@clerk/nextjs/server';
import { redirect } from 'next/navigation';
import UpgradeSuccessContent from './UpgradeSuccessContent';

export const dynamic = 'force-dynamic';

export default async function UpgradeSuccessPage() {
  const { userId } = await auth();
  if (!userId) redirect('/sign-in?redirect_url=/upgrade/success');
  return <UpgradeSuccessContent />;
}
