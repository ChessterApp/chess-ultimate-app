/**
 * Public Chess Empire onboarding landing page.
 *
 * Phase 2 of the Chess Empire → Chesster onboarding arc. Server component
 * resolves the `branchToken` against `branch_invite_tokens` (service role,
 * `resolveWelcomeToken` in lib/branch-invite-token.ts — shared with the
 * `GET /api/chess-empire/welcome/[branchToken]` JSON route) and, if valid,
 * hands the resolved `{ branchName, organizationId }` to the client state
 * machine in `WelcomeFlow`. Invalid / revoked / expired tokens
 * render a friendly "link no longer valid" screen instead of a 404.
 */
import type { Metadata } from 'next';
import { getTranslations } from 'next-intl/server';
import { resolveWelcomeToken } from '@/lib/branch-invite-token';
import WelcomeFlow from './WelcomeFlow';
import LinkInvalid from './LinkInvalid';

interface PageProps {
  params: Promise<{ branchToken: string }>;
}

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { branchToken } = await params;
  const resolved = await resolveWelcomeToken(branchToken);
  const t = await getTranslations('welcome');
  if (!resolved) {
    return { title: t('linkInvalidTitle') };
  }
  return { title: t('metaTitle', { branch: resolved.branchName }) };
}

export default async function WelcomePage({ params }: PageProps) {
  const { branchToken } = await params;
  const resolved = await resolveWelcomeToken(branchToken);

  if (!resolved) {
    const t = await getTranslations('welcome');
    return <LinkInvalid title={t('linkInvalidTitle')} body={t('linkInvalidBody')} />;
  }

  // Every kind of token — branch and online alike — uses the CE roster-search
  // flow, scoped to the token's branch. Online students are enrolled in the CE
  // Online branch first, so they match on name just like branch students.
  // Online tokens additionally get the CE Online copy and a 3-day trial CTA.
  return (
    <WelcomeFlow
      branchToken={branchToken}
      branchName={resolved.branchName}
      organizationId={resolved.organizationId}
      isOnline={resolved.kind === 'online'}
    />
  );
}
