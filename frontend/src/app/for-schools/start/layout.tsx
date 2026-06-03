import { type ReactNode } from 'react';
import { getTranslations } from 'next-intl/server';
import { WizardProvider } from '@/components/school-onboarding/WizardState';

export async function generateMetadata() {
  const t = await getTranslations('schoolOnboarding.layout');
  return {
    title: t('metaTitle'),
  };
}

export default function StartLayout({ children }: { children: ReactNode }) {
  return <WizardProvider>{children}</WizardProvider>;
}
