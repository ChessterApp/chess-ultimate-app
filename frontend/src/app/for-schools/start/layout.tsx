import { type ReactNode } from 'react';
import { WizardProvider } from '@/components/school-onboarding/WizardState';

export const metadata = {
  title: 'Launch your school — Chesster',
};

export default function StartLayout({ children }: { children: ReactNode }) {
  return <WizardProvider>{children}</WizardProvider>;
}
