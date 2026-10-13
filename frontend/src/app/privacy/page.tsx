import type { Metadata } from 'next';
import Link from 'next/link';
import { getTranslations } from 'next-intl/server';

// TODO legal: review under KZ Law 94-V on personal data before scaling

const LAST_UPDATED = '2026-10-12';
const SUPPORT_EMAIL = 'support@chesster.io';

const COLLECT_ITEMS = ['account', 'progress', 'coach', 'payment'] as const;
const PROCESSOR_ITEMS = ['clerk', 'supabase', 'whop', 'posthog', 'vercel', 'ai'] as const;

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations('privacy');
  return { title: t('metaTitle'), description: t('metaDescription') };
}

export default async function PrivacyPage() {
  const t = await getTranslations('privacy');

  return (
    <main className="mx-auto w-full max-w-2xl px-4 py-10 text-gray-800">
      <h1 className="text-3xl font-bold text-gray-900">{t('title')}</h1>
      <p className="mt-2 text-sm text-gray-500">{t('lastUpdated', { date: LAST_UPDATED })}</p>
      <p className="mt-6">{t('intro')}</p>

      <Section title={t('whoWeAre.title')}>
        <p>{t('whoWeAre.body')}</p>
      </Section>

      <Section title={t('collect.title')}>
        <p>{t('collect.intro')}</p>
        <ul className="mt-2 list-disc space-y-1 pl-6">
          {COLLECT_ITEMS.map((key) => (
            <li key={key}>{t(`collect.${key}`)}</li>
          ))}
        </ul>
      </Section>

      <Section title={t('children.title')}>
        <p>{t('children.body')}</p>
      </Section>

      <Section title={t('analytics.title')}>
        <p>{t('analytics.body')}</p>
      </Section>

      <Section title={t('processors.title')}>
        <p>{t('processors.intro')}</p>
        <ul className="mt-2 list-disc space-y-1 pl-6">
          {PROCESSOR_ITEMS.map((key) => (
            <li key={key}>{t(`processors.${key}`)}</li>
          ))}
        </ul>
      </Section>

      <Section title={t('retention.title')}>
        <p>
          {t.rich('retention.body', {
            link: (chunks) => (
              <Link href="/delete-account" className="font-semibold text-purple-600 underline">
                {chunks}
              </Link>
            ),
          })}
        </p>
      </Section>

      <Section title={t('contact.title')}>
        <p>
          {t('contact.body')}{' '}
          <a href={`mailto:${SUPPORT_EMAIL}`} className="font-semibold text-purple-600 underline">
            {SUPPORT_EMAIL}
          </a>
        </p>
      </Section>
    </main>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="mt-8">
      <h2 className="text-xl font-semibold text-gray-900">{title}</h2>
      <div className="mt-2 leading-relaxed">{children}</div>
    </section>
  );
}
