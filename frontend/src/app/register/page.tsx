/**
 * Public branch-picker registration page (`/register`).
 *
 * White-label onboarding entry point. On a tenant host the sign-in footer's
 * РЕГИСТРАЦИЯ link and the sign-up guard both land here. This server component
 * reads the resolved org from the request headers (`x-org-id`, set by
 * middleware), resolves the org's active branch-invite tokens via
 * `loadRegisterOptions` (lib/register-options.ts — shared with the
 * `GET /api/chess-empire/register/options` JSON route), and hands the options
 * to the client `RegisterPicker`.
 *
 * Each branch card links to its existing `/welcome/<token>` flow; the online
 * card links to the online-kind token's `/welcome/<token>`. An empty state
 * (contact info) renders when no active tokens exist.
 */
import type { Metadata } from 'next';
import { headers } from 'next/headers';
import { getTranslations } from 'next-intl/server';
import { loadRegisterOptions } from '@/lib/register-options';
import RegisterPicker from './RegisterPicker';

export const dynamic = 'force-dynamic';

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations('register');
  return { title: t('title') };
}

export default async function RegisterPage() {
  const headersList = await headers();
  const orgId = headersList.get('x-org-id');

  const { branches, online } = orgId
    ? await loadRegisterOptions(orgId)
    : { branches: [], online: null };

  return <RegisterPicker branches={branches} online={online} />;
}
