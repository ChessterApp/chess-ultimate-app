export default function Loading() {
  return (
    <div className="min-h-screen bg-gradient-to-b from-purple-50 to-white p-4 pb-20">
      <div className="animate-pulse flex flex-col items-center gap-4">
        {/* Board skeleton */}
        <div className="aspect-square w-full max-w-[480px] bg-gray-200 dark:bg-gray-700 rounded-xl" />
        {/* Puzzle info */}
        <div className="w-full max-w-[480px] space-y-3">
          <div className="h-6 bg-gray-200 dark:bg-gray-700 rounded w-40" />
          <div className="flex gap-2">
            <div className="h-8 bg-gray-200 dark:bg-gray-700 rounded-full w-24" />
            <div className="h-8 bg-gray-200 dark:bg-gray-700 rounded-full w-24" />
          </div>
          <div className="h-12 bg-gray-200 dark:bg-gray-700 rounded-xl" />
        </div>
      </div>
    </div>
  );
}
