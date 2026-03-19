/**
 * PageSkeleton - Loading Fallback Component
 *
 * Displays a lightweight skeleton of the app layout structure
 * while the main content is loading. Shows the sidebar, navbar,
 * and content area placeholders to maintain visual consistency.
 */
export default function PageSkeleton() {
  return (
    <div className="min-h-screen bg-white dark:bg-[#141414]">
      {/* Desktop Layout */}
      <div className="hidden md:flex min-h-screen">
        {/* Desktop Sidebar Skeleton */}
        <div className="w-16 flex-shrink-0 bg-white dark:bg-[#141414] border-r border-gray-200 dark:border-[#2a2a2a]">
          <div className="flex flex-col items-center py-4 space-y-6">
            {/* Logo placeholder */}
            <div className="w-10 h-10 rounded-lg bg-gray-200 dark:bg-[#2a2a2a] animate-pulse" />
            {/* Nav items placeholders */}
            {[...Array(5)].map((_, i) => (
              <div
                key={i}
                className="w-10 h-10 rounded-lg bg-gray-200 dark:bg-[#2a2a2a] animate-pulse"
                style={{ animationDelay: `${i * 0.1}s` }}
              />
            ))}
          </div>
        </div>

        {/* Main Content Area Skeleton */}
        <div className="flex-1 min-w-0 p-6">
          {/* Content blocks */}
          <div className="space-y-4">
            {/* Header block */}
            <div className="h-8 w-64 bg-gray-200 dark:bg-[#2a2a2a] rounded animate-pulse" />

            {/* Content blocks */}
            {[...Array(3)].map((_, i) => (
              <div
                key={i}
                className="h-32 bg-gray-100 dark:bg-[#1a1a1a] rounded-lg animate-pulse"
                style={{ animationDelay: `${(i + 1) * 0.15}s` }}
              />
            ))}
          </div>
        </div>
      </div>

      {/* Mobile Layout */}
      <div className="md:hidden min-h-screen flex flex-col">
        {/* Mobile Top Navbar Skeleton */}
        <div className="h-14 bg-white dark:bg-[#141414] border-b border-gray-100 dark:border-[#2a2a2a]">
          <div className="flex items-center justify-between px-4 h-full">
            <div className="w-32 h-8 bg-gray-200 dark:bg-[#2a2a2a] rounded animate-pulse" />
            <div className="w-8 h-8 bg-gray-200 dark:bg-[#2a2a2a] rounded-full animate-pulse" />
          </div>
        </div>

        {/* Mobile Content Area Skeleton */}
        <div className="flex-1 p-4 pb-20">
          <div className="space-y-4">
            {/* Header block */}
            <div className="h-8 w-48 bg-gray-200 dark:bg-[#2a2a2a] rounded animate-pulse" />

            {/* Content blocks */}
            {[...Array(4)].map((_, i) => (
              <div
                key={i}
                className="h-24 bg-gray-100 dark:bg-[#1a1a1a] rounded-lg animate-pulse"
                style={{ animationDelay: `${(i + 1) * 0.15}s` }}
              />
            ))}
          </div>
        </div>

        {/* Mobile Bottom Navigation Skeleton */}
        <div className="fixed bottom-0 left-0 right-0 h-16 bg-white dark:bg-[#141414] border-t border-gray-100 dark:border-[#2a2a2a]">
          <div className="flex items-center justify-around h-full px-4">
            {[...Array(5)].map((_, i) => (
              <div
                key={i}
                className="w-6 h-6 bg-gray-200 dark:bg-[#2a2a2a] rounded animate-pulse"
                style={{ animationDelay: `${i * 0.1}s` }}
              />
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
