/**
 * `/dashboard` router.
 *
 * On the chess-empire tenant host (`chess-empire.chesster.io`), this route
 * hands off to the personalized Chess Empire homepage — same data-fetching
 * pipeline that powers the apex `/`. Everywhere else it renders the generic
 * Chesster dashboard unchanged.
 */
import { headers } from 'next/headers';
import { renderEmpireHomepage } from '@/lib/empire-homepage-render';
import ChessterDashboard from './ChessterDashboard';

export const dynamic = 'force-dynamic';

export default async function DashboardPage() {
  const headersList = await headers();
  const orgId = headersList.get('x-org-id');
  const orgSlug = headersList.get('x-org-slug');

  if (orgId && orgSlug === 'chess-empire') {
    const empire = await renderEmpireHomepage(orgId);
    if (empire) return empire;
  }

  return <ChessterDashboard />;
}
