import { resolveCeLevelFloor } from '@/lib/learn-ce-floor';
import { resolveMembershipState } from '@/lib/access-membership';
import { getAccessPolicy } from '@/lib/access-policy';
import LearnClient from './LearnClient';

export const dynamic = 'force-dynamic';

export default async function LearnPage() {
  // Reuse the same membership resolver the root layout / requireAccess use — no
  // duplicate fetch logic. The policy drives the restricted Learn ceiling.
  const [ceLevelFloor, membershipState] = await Promise.all([
    resolveCeLevelFloor(),
    resolveMembershipState(),
  ]);
  const policy = getAccessPolicy(membershipState);
  return <LearnClient ceLevelFloor={ceLevelFloor} policy={policy} />;
}
