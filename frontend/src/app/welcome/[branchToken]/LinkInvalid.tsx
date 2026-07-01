/**
 * Friendly fallback shown when a branch invite token is unknown, revoked, or
 * expired. Sync server component; receives translated strings from the parent
 * to keep the JSX directly renderable from tests.
 */
import Image from 'next/image';

interface LinkInvalidProps {
  title: string;
  body: string;
}

export default function LinkInvalid({ title, body }: LinkInvalidProps) {
  return (
    <div className="flex flex-col items-center justify-start pt-16 md:justify-center md:pt-0 min-h-screen bg-purple-600 md:bg-gray-50 px-4 pb-[env(safe-area-inset-bottom)]">
      <div className="w-full max-w-md bg-white md:bg-white rounded-3xl p-6 md:p-8 mt-4 md:mt-0 shadow-xl">
        <div className="text-center">
          <div className="bg-white rounded-full inline-flex items-center justify-center shadow-lg mb-4 w-24 h-24 md:w-28 md:h-28 overflow-hidden">
            <Image
              src="/static/images/chesster-logo-v3.png"
              alt="Chesster"
              width={112}
              height={112}
              className="w-full h-full object-contain"
              priority
            />
          </div>
          <h1 className="text-2xl font-bold text-gray-800">{title}</h1>
          <p className="text-sm text-gray-500 mt-3">{body}</p>
        </div>
      </div>
    </div>
  );
}
