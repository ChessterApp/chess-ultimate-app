/**
 * Public Chess Empire onboarding landing page.
 *
 * Phase 2 of the Chess Empire → Chesster onboarding arc. Server component
 * resolves the `branchToken` against `branch_invite_tokens` (service role)
 * and, if valid, hands the resolved `{ branchName, organizationId }` to the
 * client state machine in `WelcomeFlow`. Invalid / revoked / expired tokens
 * render a friendly "link no longer valid" screen instead of a 404.
 */
import type { Metadata } from 'next';
import { getTranslations } from 'next-intl/server';
import { supabaseAdmin } from '@/lib/supabase-admin';
import WelcomeFlow from './WelcomeFlow';
import LinkInvalid from './LinkInvalid';

interface BranchTokenRow {
  organization_id: string;
  external_branch_id: string;
  branch_name: string;
  expires_at: string | null;
  revoked_at: string | null;
}

interface ResolvedToken {
  branchName: string;
  organizationId: string;
  externalBranchId: string;
}

async function resolveBranchToken(token: string): Promise<ResolvedToken | null> {
  if (!token) return null;
  const { data, error } = await supabaseAdmin
    .from('branch_invite_tokens')
    .select('organization_id, external_branch_id, branch_name, expires_at, revoked_at')
    .eq('token', token)
    .maybeSingle();
  if (error || !data) return null;
  const row = data as BranchTokenRow;
  if (row.revoked_at) return null;
  if (row.expires_at && new Date(row.expires_at).getTime() < Date.now()) return null;
  return {
    branchName: row.branch_name,
    organizationId: row.organization_id,
    externalBranchId: row.external_branch_id,
  };
}

interface PageProps {
  params: Promise<{ branchToken: string }>;
}

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { branchToken } = await params;
  const resolved = await resolveBranchToken(branchToken);
  const t = await getTranslations('welcome');
  if (!resolved) {
    return { title: t('linkInvalidTitle') };
  }
  return { title: t('metaTitle', { branch: resolved.branchName }) };
}

export default async function WelcomePage({ params }: PageProps) {
  const { branchToken } = await params;
  const resolved = await resolveBranchToken(branchToken);

  if (!resolved) {
    const t = await getTranslations('welcome');
    return <LinkInvalid title={t('linkInvalidTitle')} body={t('linkInvalidBody')} />;
  }

  return (
    <WelcomeFlow
      branchToken={branchToken}
      branchName={resolved.branchName}
      organizationId={resolved.organizationId}
    />
  );
}
