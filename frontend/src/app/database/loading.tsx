import { INSTANT_LOADING } from '@/lib/feature-flags';

export default function Loading() {
  if (INSTANT_LOADING) {
    return <div className="min-h-screen bg-gradient-to-b from-purple-50 to-white dark:from-[#141414] dark:to-[#141414] p-4 pb-20" />;
  }

  return (
    <div className="min-h-screen bg-gradient-to-b from-purple-50 to-white p-4 pb-20">
      <div className="animate-pulse flex flex-col lg:flex-row gap-4">
        {/* Chess board skeleton */}
        <div className="flex-shrink-0">
          <div className="aspect-square w-full max-w-[480px] bg-gray-200 dark:bg-gray-700 rounded-xl" />
        </div>
        {/* Move list / side panel */}
        <div className="flex-1 space-y-3">
          <div className="h-6 bg-gray-200 dark:bg-gray-700 rounded w-48 mb-4" />
          <div className="h-10 bg-gray-200 dark:bg-gray-700 rounded-lg" />
          <div className="h-10 bg-gray-200 dark:bg-gray-700 rounded-lg" />
          <div className="h-10 bg-gray-200 dark:bg-gray-700 rounded-lg" />
          <div className="h-10 bg-gray-200 dark:bg-gray-700 rounded-lg" />
          <div className="h-10 bg-gray-200 dark:bg-gray-700 rounded-lg" />
          <div className="h-10 bg-gray-200 dark:bg-gray-700 rounded-lg w-3/4" />
        </div>
      </div>
    </div>
  );
}
