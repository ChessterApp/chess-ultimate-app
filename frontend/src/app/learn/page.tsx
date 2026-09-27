import { resolveCeLevelFloor } from '@/lib/learn-ce-floor';
import { resolveAccessPolicy } from '@/lib/access-membership';
import LearnClient from './LearnClient';

export const dynamic = 'force-dynamic';

export default async function LearnPage() {
  // Reuse the same policy resolver the root layout / requireAccess use (personal
  // subscription override included) — no duplicate fetch logic. The policy drives
  // the restricted Learn ceiling.
  const [ceLevelFloor, policy] = await Promise.all([
    resolveCeLevelFloor(),
    resolveAccessPolicy(),
  ]);
  return <LearnClient ceLevelFloor={ceLevelFloor} policy={policy} />;
}
