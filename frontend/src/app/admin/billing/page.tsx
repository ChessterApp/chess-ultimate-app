'use client';

import { useOrganization } from '@/contexts/OrganizationContext';

const TIERS = [
  { name: 'Starter', price: 0, students: 10, features: ['Basic dashboard', 'Student management', 'Course assignments'] },
  { name: 'Growth', price: 29, students: 50, features: ['Everything in Starter', 'Tournaments', 'Analytics', 'Custom branding'] },
  { name: 'Pro', price: 79, students: 200, features: ['Everything in Growth', 'FIDE rating sync', 'API access', 'Priority support'] },
  { name: 'Enterprise', price: null, students: null, features: ['Everything in Pro', 'Unlimited students', 'SSO', 'Dedicated support'] },
];

const PLACEHOLDER_INVOICES = [
  { id: 'INV-001', date: '2026-04-01', amount: 29, status: 'paid' },
  { id: 'INV-002', date: '2026-03-01', amount: 29, status: 'paid' },
  { id: 'INV-003', date: '2026-02-01', amount: 29, status: 'paid' },
];

function StatusBadge({ status }: { status: string }) {
  const colors: Record<string, string> = {
    paid: 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-300',
    pending: 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-300',
    overdue: 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300',
  };

  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${colors[status] || colors.pending}`}>
      {status}
    </span>
  );
}

export default function AdminBillingPage() {
  const { org } = useOrganization();
  const currentTier = TIERS[1]; // Placeholder: assume Growth plan
  const studentCount = 12; // Placeholder

  return (
    <div>
      <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100 mb-6">
        Billing
      </h1>

      {/* Current Plan */}
      <section className="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 p-6 mb-6">
        <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-4">Current Plan</h2>
        <div className="flex items-baseline gap-2 mb-2">
          <span className="text-3xl font-semibold text-gray-900 dark:text-gray-100">{currentTier.name}</span>
          <span className="text-sm text-gray-500 dark:text-gray-400">
            — ${currentTier.price}/month
          </span>
        </div>
        <p className="text-sm text-gray-500 dark:text-gray-400 mb-4">
          {studentCount} / {currentTier.students} students used
        </p>
        <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-2 mb-4">
          <div
            className="h-2 rounded-full"
            style={{
              width: `${Math.min(100, (studentCount / (currentTier.students || 1)) * 100)}%`,
              backgroundColor: 'var(--brand-primary)',
            }}
          />
        </div>
        <p className="text-xs text-gray-500 dark:text-gray-400">
          Whop integration coming soon. Contact support to change plans.
        </p>
      </section>

      {/* Pricing Tiers */}
      <section className="mb-6">
        <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-4">Plans</h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {TIERS.map(tier => {
            const isCurrent = tier.name === currentTier.name;
            return (
              <div
                key={tier.name}
                className={`rounded-xl border p-5 ${
                  isCurrent
                    ? 'border-blue-500 dark:border-blue-400 bg-blue-50 dark:bg-blue-900/10'
                    : 'border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800'
                }`}
              >
                <h3 className="font-semibold text-gray-900 dark:text-gray-100">{tier.name}</h3>
                <p className="mt-1 text-2xl font-bold text-gray-900 dark:text-gray-100">
                  {tier.price !== null ? `$${tier.price}` : 'Custom'}
                  {tier.price !== null && <span className="text-sm font-normal text-gray-500">/mo</span>}
                </p>
                <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                  {tier.students !== null ? `Up to ${tier.students} students` : 'Unlimited students'}
                </p>
                <ul className="mt-3 space-y-1">
                  {tier.features.map(f => (
                    <li key={f} className="text-xs text-gray-600 dark:text-gray-400 flex items-start gap-1">
                      <span className="text-green-500 mt-0.5">&#10003;</span> {f}
                    </li>
                  ))}
                </ul>
                {isCurrent && (
                  <div className="mt-3 text-xs font-medium text-blue-600 dark:text-blue-400">Current Plan</div>
                )}
              </div>
            );
          })}
        </div>
      </section>

      {/* Invoices */}
      <section className="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800">
        <div className="px-6 py-4 border-b border-gray-200 dark:border-gray-700">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100">Invoices</h2>
        </div>
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-200 dark:border-gray-700">
              <th className="text-left px-4 py-3 font-medium text-gray-500 dark:text-gray-400">Invoice</th>
              <th className="text-left px-4 py-3 font-medium text-gray-500 dark:text-gray-400">Date</th>
              <th className="text-left px-4 py-3 font-medium text-gray-500 dark:text-gray-400">Amount</th>
              <th className="text-left px-4 py-3 font-medium text-gray-500 dark:text-gray-400">Status</th>
            </tr>
          </thead>
          <tbody>
            {PLACEHOLDER_INVOICES.map(inv => (
              <tr key={inv.id} className="border-b border-gray-100 dark:border-gray-700 last:border-0">
                <td className="px-4 py-3 font-medium text-gray-900 dark:text-gray-100">{inv.id}</td>
                <td className="px-4 py-3 text-gray-500 dark:text-gray-400">{inv.date}</td>
                <td className="px-4 py-3 text-gray-900 dark:text-gray-100">${inv.amount}</td>
                <td className="px-4 py-3"><StatusBadge status={inv.status} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  );
}
