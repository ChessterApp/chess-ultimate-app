import Link from 'next/link';
import { getTranslations } from 'next-intl/server';

export async function generateMetadata() {
  const t = await getTranslations('schoolOnboarding.marketing');
  return {
    title: t('metaTitle'),
    description: t('metaDescription'),
  };
}

export default async function ForSchoolsLanding() {
  const t = await getTranslations('schoolOnboarding.marketing');

  return (
    <div className="min-h-screen bg-white text-gray-900">
      <main className="max-w-4xl mx-auto px-4 sm:px-6 py-12 sm:py-20">
        <h1 className="text-3xl sm:text-4xl md:text-5xl font-bold tracking-tight">
          {t('heading')}
        </h1>
        <p className="mt-6 text-lg text-gray-600 max-w-2xl">{t('lede')}</p>

        <div className="mt-10 flex flex-wrap gap-3">
          <Link
            href="/for-schools/start"
            className="inline-flex items-center justify-center rounded-lg bg-blue-600 px-5 py-3 text-white font-semibold hover:bg-blue-700"
          >
            {t('ctaPrimary')}
          </Link>
          <Link
            href="/admin/billing"
            className="inline-flex items-center justify-center rounded-lg border border-gray-300 px-5 py-3 text-gray-800 hover:bg-gray-50"
          >
            {t('ctaSecondary')}
          </Link>
        </div>

        <ul className="mt-16 grid grid-cols-1 md:grid-cols-3 gap-6">
          <li className="rounded-xl border border-gray-200 p-5">
            <h3 className="font-semibold">{t('pillarBrandedTitle')}</h3>
            <p className="mt-2 text-sm text-gray-600">
              {t.rich('pillarBrandedDesc', {
                em: chunks => <em>{chunks}</em>,
              })}
            </p>
          </li>
          <li className="rounded-xl border border-gray-200 p-5">
            <h3 className="font-semibold">{t('pillarSelfServeTitle')}</h3>
            <p className="mt-2 text-sm text-gray-600">{t('pillarSelfServeDesc')}</p>
          </li>
          <li className="rounded-xl border border-gray-200 p-5">
            <h3 className="font-semibold">{t('pillarGuaranteeTitle')}</h3>
            <p className="mt-2 text-sm text-gray-600">{t('pillarGuaranteeDesc')}</p>
          </li>
        </ul>
      </main>
    </div>
  );
}
