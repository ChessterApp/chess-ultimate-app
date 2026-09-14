'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@clerk/nextjs';
import { useTranslations } from 'next-intl';
import { useSubscription } from '@/hooks/useSubscription';
import LoadingScreen from '@/components/LoadingScreen';
import UpgradePrompt from '@/components/UpgradePrompt';
import WheelGame from '@/components/wheel/WheelGame';

export default function WheelPage() {
  const { isSignedIn, isLoaded } = useAuth();
  const subscription = useSubscription();
  const router = useRouter();
  const t = useTranslations('wheel');

  // Redirect unauthenticated users to sign-in (same pattern as /coach).
  useEffect(() => {
    if (isLoaded && !isSignedIn) {
      router.push('/sign-in');
    }
  }, [isLoaded, isSignedIn, router]);

  if (!isLoaded || subscription.loading) {
    return <LoadingScreen isVisible={true} />;
  }

  if (!isSignedIn) {
    return null; // Will redirect via useEffect
  }

  if (!subscription.active) {
    return <UpgradePrompt feature={t('feature')} />;
  }

  return <WheelGame />;
}
