/**
 * Duplicate-account screen shown when a parent reaches the DOB step for a
 * student who is already linked to a Chesster account (verify returned 409
 * `ALREADY_REGISTERED`). Static server component — no token resolution
 * happens here; the client redirects to this URL only as a friendly stop.
 *
 * The "Contact" button is a placeholder mailto. Real WhatsApp / support
 * email needs to be confirmed by Chess Empire before launch (see report).
 */
import type { Metadata } from 'next';
import Link from 'next/link';
import Image from 'next/image';
import { getTranslations } from 'next-intl/server';

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations('welcome.registered');
  return { title: t('title') };
}

const CONTACT_HREF = 'mailto:hello@chess-empire.kz';

export default async function RegisteredPage() {
  const t = await getTranslations('welcome.registered');
  return (
    <div className="flex flex-col items-center justify-start pt-16 md:justify-center md:pt-0 min-h-screen bg-purple-600 md:bg-gray-50 px-4 pb-[env(safe-area-inset-bottom)]">
      <div className="w-full max-w-md bg-white rounded-3xl p-6 md:p-8 mt-4 md:mt-0 shadow-xl">
        <div className="text-center mb-6">
          <div className="bg-white rounded-full inline-flex items-center justify-center shadow-lg w-24 h-24 md:w-28 md:h-28 overflow-hidden">
            <Image
              src="/static/images/chesster-logo-v3.png"
              alt="Chesster"
              width={112}
              height={112}
              className="w-full h-full object-contain"
              priority
            />
          </div>
        </div>
        <h1 className="text-2xl font-bold text-gray-800 text-center">
          {t('title')}
        </h1>
        <p className="text-sm text-gray-500 mt-3 text-center">{t('body')}</p>

        <Link
          href="/sign-in"
          className="mt-6 block w-full text-center bg-purple-600 hover:bg-purple-700 rounded-2xl py-4 font-bold uppercase tracking-wide text-white border-b-4 border-purple-800 active:border-b-2 active:translate-y-0.5 transition-all"
        >
          {t('signIn')}
        </Link>
        <a
          href={CONTACT_HREF}
          className="mt-3 block w-full text-center rounded-2xl border-2 border-gray-200 py-3 font-semibold text-gray-700 hover:bg-gray-50"
        >
          {t('contact')}
        </a>
      </div>
    </div>
  );
}
