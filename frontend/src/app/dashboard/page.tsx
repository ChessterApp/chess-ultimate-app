/**
 * `/dashboard` router.
 *
 * On the chess-empire tenant host (`chess-empire.chesster.io`), this route
 * hands off to the personalized Chess Empire homepage — same data-fetching
 * pipeline that powers the apex `/`. Everywhere else it renders the generic
 * Chesster dashboard unchanged.
 */
import { headers } from 'next/headers';
import { redirect } from 'next/navigation';
import { renderEmpireHomepage } from '@/lib/empire-homepage-render';
import ChessterDashboard from './ChessterDashboard';
import EmpireError from './EmpireError';

export const dynamic = 'force-dynamic';

export default async function DashboardPage() {
  const headersList = await headers();
  const orgId = headersList.get('x-org-id');
  const orgSlug = headersList.get('x-org-slug');

  if (orgId && orgSlug === 'chess-empire') {
    // On the tenant host we NEVER fall back to the generic ChessterDashboard —
    // that masked real auth/lookup failures as "personalization missing". Map
    // each distinct state to an honest outcome instead.
    const result = await renderEmpireHomepage(orgId);
    if (result.status === 'auth_null') {
      // Stale/absent server session — bounce through sign-in and return here.
      redirect('/sign-in?redirect_url=/dashboard');
    }
    if (result.status === 'lookup_error') {
      return <EmpireError />;
    }
    // 'ok' | 'no_link' — render the personalized node.
    return result.node;
  }

  return <ChessterDashboard />;
}
