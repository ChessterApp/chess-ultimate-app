'use client';

import { useOrganization } from '@/contexts/OrganizationContext';
import ClerkMembersPanel from './ClerkMembersPanel';
import ChessEmpirePanel from './ChessEmpirePanel';

export default function AdminStudentsPage() {
  const { org } = useOrganization();
  if (org?.slug === 'chess-empire') {
    return <ChessEmpirePanel />;
  }
  return <ClerkMembersPanel />;
}
