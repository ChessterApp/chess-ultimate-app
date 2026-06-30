/**
 * @vitest-environment jsdom
 *
 * Slug-gated switch: the apex `/admin/students` page should render
 * <ChessEmpirePanel /> for slug === 'chess-empire' and <ClerkMembersPanel />
 * for everyone else (byte-equivalent default behaviour).
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import React from 'react';
import { cleanup, render } from '@testing-library/react';

const orgRef: { current: { id: string; slug: string } | null } = {
  current: { id: 'org-other', slug: 'some-school' },
};

vi.mock('@/contexts/OrganizationContext', () => ({
  useOrganization: () => ({
    org: orgRef.current,
    isWhiteLabel: !!orgRef.current,
  }),
}));

vi.mock('../ClerkMembersPanel', () => ({
  __esModule: true,
  default: () => <div data-testid="clerk-panel" />,
}));

vi.mock('../ChessEmpirePanel', () => ({
  __esModule: true,
  default: () => <div data-testid="ce-panel" />,
}));

import AdminStudentsPage from '../page';

beforeEach(() => {
  vi.clearAllMocks();
});
afterEach(() => cleanup());

describe('AdminStudentsPage slug-gated switch', () => {
  it('renders ChessEmpirePanel when slug === chess-empire', () => {
    orgRef.current = { id: 'org-ce', slug: 'chess-empire' };
    const { getByTestId, queryByTestId } = render(<AdminStudentsPage />);
    expect(getByTestId('ce-panel')).toBeTruthy();
    expect(queryByTestId('clerk-panel')).toBeNull();
  });

  it('renders ClerkMembersPanel for every other slug', () => {
    orgRef.current = { id: 'org-other', slug: 'some-school' };
    const { getByTestId, queryByTestId } = render(<AdminStudentsPage />);
    expect(getByTestId('clerk-panel')).toBeTruthy();
    expect(queryByTestId('ce-panel')).toBeNull();
  });

  it('renders ClerkMembersPanel when org is null', () => {
    orgRef.current = null;
    const { getByTestId, queryByTestId } = render(<AdminStudentsPage />);
    expect(getByTestId('clerk-panel')).toBeTruthy();
    expect(queryByTestId('ce-panel')).toBeNull();
  });
});
