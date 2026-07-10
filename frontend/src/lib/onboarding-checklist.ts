// PRD §11.2 #5 — In-dashboard 24h onboarding checklist.
//
// Pure derivation: takes an org snapshot + member counts and returns the
// checklist state. UI imports `<OnboardingChecklist>` which renders this
// output; unit tests cover the derivation function without a DOM.

export type ChecklistItemId =
  | 'upload_logo'
  | 'pick_colors'
  | 'invite_students'
  | 'invite_teacher'
  | 'verify_sender'
  | 'connect_domain';

export interface ChecklistItem {
  id: ChecklistItemId;
  href: string;
  completed: boolean;
  /** True when the item is hidden for the current tier (e.g. Pro-only). */
  hidden?: boolean;
}

export interface ChecklistSnapshot {
  org: {
    logoUrl?: string | null;
    primaryColor?: string | null;
    secondaryColor?: string | null;
    accentColor?: string | null;
    customDomainStatus?: string | null;
    emailSenderStatus?: string | null;
    createdAt?: string | null;
    plan?: string | null;
  };
  studentCount: number;
  teacherCount: number;
}

const DEFAULT_PRIMARY = '#1a73e8';

export function computeChecklist(snap: ChecklistSnapshot): ChecklistItem[] {
  const { org, studentCount, teacherCount } = snap;
  const isPro = org.plan === 'pro' || org.plan === 'enterprise';
  const hasCustomColors =
    Boolean(org.primaryColor) && org.primaryColor !== DEFAULT_PRIMARY;

  const items: ChecklistItem[] = [
    {
      id: 'upload_logo',
      href: '/admin/settings',
      completed: Boolean(org.logoUrl),
    },
    {
      id: 'pick_colors',
      href: '/admin/settings',
      completed: hasCustomColors,
    },
    {
      id: 'invite_students',
      href: '/admin/students',
      completed: studentCount >= 5,
    },
    {
      id: 'invite_teacher',
      href: '/admin/students',
      completed: teacherCount >= 1,
    },
    {
      id: 'verify_sender',
      href: '/admin/settings/sender-domain',
      completed: org.emailSenderStatus === 'active',
      hidden: !isPro,
    },
    {
      id: 'connect_domain',
      href: '/admin/settings/domain',
      completed: org.customDomainStatus === 'active',
      hidden: !isPro,
    },
  ];
  return items;
}

export function completionPercentage(items: ChecklistItem[]): number {
  const visible = items.filter(i => !i.hidden);
  if (visible.length === 0) return 100;
  const done = visible.filter(i => i.completed).length;
  return Math.round((done / visible.length) * 100);
}

export function isAllCompleted(items: ChecklistItem[]): boolean {
  return completionPercentage(items) === 100;
}

/**
 * The checklist is shown for 7 days after org creation, or until 100%
 * complete. Returns true when it should be visible.
 */
export function shouldShowChecklist(snap: ChecklistSnapshot, now = new Date()): boolean {
  const items = computeChecklist(snap);
  if (isAllCompleted(items)) return false;
  if (!snap.org.createdAt) return true;
  const created = new Date(snap.org.createdAt);
  if (Number.isNaN(created.getTime())) return true;
  const ageMs = now.getTime() - created.getTime();
  const sevenDays = 7 * 24 * 60 * 60 * 1000;
  return ageMs <= sevenDays;
}
