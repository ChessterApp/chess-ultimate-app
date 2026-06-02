import Link from 'next/link';

export const metadata = {
  title: 'Chesster for Schools — Launch your branded chess platform',
  description:
    'Run your own white-label chess school. Logo, colors, domain, students invited — in 15 minutes.',
};

export default function ForSchoolsLanding() {
  return (
    <div className="min-h-screen bg-white text-gray-900">
      <main className="max-w-4xl mx-auto px-6 py-20">
        <h1 className="text-5xl font-bold tracking-tight">
          Your school. Your brand. Live in 15 minutes.
        </h1>
        <p className="mt-6 text-lg text-gray-600 max-w-2xl">
          Chesster powers chess academies that want a real product, not a
          spreadsheet. Pick a subdomain, drop in your logo, invite your
          students — and your platform is live.
        </p>

        <div className="mt-10 flex flex-wrap gap-3">
          <Link
            href="/for-schools/start"
            className="inline-flex items-center justify-center rounded-lg bg-blue-600 px-5 py-3 text-white font-semibold hover:bg-blue-700"
          >
            Launch your school in 15 minutes →
          </Link>
          <Link
            href="/admin/billing"
            className="inline-flex items-center justify-center rounded-lg border border-gray-300 px-5 py-3 text-gray-800 hover:bg-gray-50"
          >
            See pricing
          </Link>
        </div>

        <ul className="mt-16 grid grid-cols-1 md:grid-cols-3 gap-6">
          <li className="rounded-xl border border-gray-200 p-5">
            <h3 className="font-semibold">Branded</h3>
            <p className="mt-2 text-sm text-gray-600">
              Your logo, colors, and domain. Parents see <em>your</em> school.
            </p>
          </li>
          <li className="rounded-xl border border-gray-200 p-5">
            <h3 className="font-semibold">Self-serve</h3>
            <p className="mt-2 text-sm text-gray-600">
              No demo calls. Sign up, pay, invite students — same session.
            </p>
          </li>
          <li className="rounded-xl border border-gray-200 p-5">
            <h3 className="font-semibold">30-day money-back</h3>
            <p className="mt-2 text-sm text-gray-600">
              Try the full platform risk-free. Cancel any time.
            </p>
          </li>
        </ul>
      </main>
    </div>
  );
}
