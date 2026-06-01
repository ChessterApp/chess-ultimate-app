import Link from 'next/link';

export const dynamic = 'force-dynamic';

export default function SuperAdminHome() {
  return (
    <div className="max-w-3xl space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">
          Platform Admin
        </h1>
        <p className="mt-2 text-sm text-gray-600 dark:text-gray-400">
          Manage all Chesster users and partner schools from here. Every action
          is recorded in the audit log.
        </p>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <Link
          href="/super-admin/users"
          className="block p-5 bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 hover:border-blue-400 dark:hover:border-blue-500 transition-colors"
        >
          <h2 className="text-base font-semibold text-gray-900 dark:text-gray-100">
            Users →
          </h2>
          <p className="mt-1 text-sm text-gray-600 dark:text-gray-400">
            Search, suspend, refund, and impersonate (read-only) any Chesster user.
          </p>
        </Link>

        <Link
          href="/super-admin/schools"
          className="block p-5 bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 hover:border-blue-400 dark:hover:border-blue-500 transition-colors"
        >
          <h2 className="text-base font-semibold text-gray-900 dark:text-gray-100">
            Schools →
          </h2>
          <p className="mt-1 text-sm text-gray-600 dark:text-gray-400">
            List partner organizations, drill into one, and suspend, unsuspend, or
            promote a member to owner.
          </p>
        </Link>
      </div>
    </div>
  );
}
