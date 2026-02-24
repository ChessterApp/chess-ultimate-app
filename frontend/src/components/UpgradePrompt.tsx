'use client';

import { useSubscription } from '@/hooks/useSubscription';
import { useRouter } from 'next/navigation';
import { useTranslations } from 'next-intl';

export default function UpgradePrompt({ feature }: { feature?: string }) {
  const { active, loading } = useSubscription();
  const router = useRouter();
  const t = useTranslations('upgradePrompt');

  if (loading || active) return null;

  return (
    <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4">
      <div className="bg-white dark:bg-gray-900 rounded-2xl p-8 max-w-md w-full text-center shadow-2xl">
        <div className="text-5xl mb-4">👑</div>
        <h2 className="text-2xl font-bold mb-2">{t('title')}</h2>
        <p className="text-gray-500 dark:text-gray-400 mb-6">
          {feature
            ? t('description', { feature })
            : t('descriptionGeneric')}
        </p>
        <button
          onClick={() => router.push('/onboarding')}
          className="w-full bg-purple-600 text-white font-bold py-3 rounded-full hover:bg-purple-700 transition-colors"
        >
          {t('viewPlans')}
        </button>
        <button
          onClick={() => window.history.back()}
          className="mt-3 text-gray-400 text-sm hover:text-gray-600"
        >
          {t('maybeLater')}
        </button>
      </div>
    </div>
  );
}
