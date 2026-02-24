export default function Loading() {
  return (
    <div className="min-h-screen bg-gradient-to-b from-purple-50 to-white p-4 pb-20">
      <div className="animate-pulse flex flex-col lg:flex-row gap-4">
        {/* Board skeleton */}
        <div className="flex-shrink-0">
          <div className="aspect-square w-full max-w-[480px] bg-gray-200 dark:bg-gray-700 rounded-xl" />
        </div>
        {/* Analysis panel */}
        <div className="flex-1 space-y-3">
          <div className="h-8 bg-gray-200 dark:bg-gray-700 rounded w-56 mb-2" />
          <div className="h-24 bg-gray-200 dark:bg-gray-700 rounded-xl" />
          <div className="h-6 bg-gray-200 dark:bg-gray-700 rounded w-40" />
          <div className="h-40 bg-gray-200 dark:bg-gray-700 rounded-xl" />
          <div className="h-12 bg-gray-200 dark:bg-gray-700 rounded-xl" />
        </div>
      </div>
    </div>
  );
}
