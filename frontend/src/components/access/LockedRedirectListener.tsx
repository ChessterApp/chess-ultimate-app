'use client';

/**
 * Opens the LockedFeatureModal when a restricted member is bounced to
 * `/dashboard?locked=<featureKey>` by the `requireAccess` server guard (Task 5).
 * Mounted once in the app shell. Reads the `locked` query param; on dismiss it
 * strips the param so the modal doesn't reappear on refresh. Wrapped in a
 * Suspense boundary because `useSearchParams` opts the tree into client
 * rendering.
 */
import { Suspense } from 'react';
import { useSearchParams, useRouter, usePathname } from 'next/navigation';
import { useMembership } from '@/components/providers/MembershipProvider';
import LockedFeatureModal from './LockedFeatureModal';

function LockedRedirect() {
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const { policy } = useMembership();

  const locked = params?.get('locked');
  if (!locked || policy.mode !== 'restricted') return null;

  return (
    <LockedFeatureModal
      featureKey={locked}
      reason={policy.reason}
      upgradePath={policy.upgradePath}
      onClose={() => router.replace(pathname ?? '/dashboard')}
    />
  );
}

export default function LockedRedirectListener() {
  return (
    <Suspense fallback={null}>
      <LockedRedirect />
    </Suspense>
  );
}
