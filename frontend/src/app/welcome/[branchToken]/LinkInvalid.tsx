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
          <div className="bg-white rounded-full p-3 md:p-4 inline-block shadow-lg mb-4">
            <Image
              src="/static/images/chesster-logo-v3.png"
              alt="Chesster"
              width={64}
              height={64}
              className="w-12 h-12 md:w-16 md:h-16"
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
