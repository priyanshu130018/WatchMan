import { Skeleton } from "@/components/ui/skeleton";
import { CONTENT_PAGE_SIZE } from "@/lib/constants";

export function ContentCardSkeleton() {
  return (
    <div aria-hidden="true">
      <Skeleton className="aspect-[2/3] w-full rounded-xl" />
      <Skeleton className="mt-3 h-3.5 w-4/5" />
      <Skeleton className="mt-2 h-3 w-2/5" />
    </div>
  );
}

export function ContentGridSkeleton({ count = CONTENT_PAGE_SIZE }: { count?: number }) {
  return (
    <ul
      className="grid grid-cols-2 gap-4 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6"
      aria-busy="true"
      aria-label="Loading content"
    >
      {Array.from({ length: count }).map((_, i) => (
        <li key={i}>
          <ContentCardSkeleton />
        </li>
      ))}
    </ul>
  );
}

export function SectionSkeleton() {
  return (
    <div className="pt-11" aria-busy="true" aria-label="Loading section">
      <div className="mb-4 flex items-end justify-between">
        <div className="space-y-2">
          <Skeleton className="h-3 w-24" />
          <Skeleton className="h-6 w-48" />
        </div>
        <Skeleton className="h-4 w-16" />
      </div>
      <div className="-mx-1 flex gap-4 overflow-hidden px-1 pb-4">
        {Array.from({ length: 6 }).map((_, i) => (
          <div key={i} className="w-[42vw] shrink-0 sm:w-[30vw] md:w-44 lg:w-48">
            <ContentCardSkeleton />
          </div>
        ))}
      </div>
    </div>
  );
}

export function DetailSkeleton() {
  return (
    <div
      className="mx-auto max-w-[1400px] px-4 pt-10 sm:px-7"
      aria-busy="true"
      aria-label="Loading details"
    >
      <div className="grid gap-10 md:grid-cols-[230px_1fr]">
        <Skeleton className="aspect-[2/3] w-full max-w-[230px] rounded-2xl" />
        <div className="space-y-4">
          <Skeleton className="h-12 w-3/4" />
          <Skeleton className="h-5 w-1/3" />
          <div className="flex gap-2">
            <Skeleton className="h-7 w-20 rounded-full" />
            <Skeleton className="h-7 w-20 rounded-full" />
            <Skeleton className="h-7 w-20 rounded-full" />
          </div>
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-4 w-2/3" />
        </div>
      </div>
    </div>
  );
}

export function PageSkeleton() {
  return (
    <div className="mx-auto max-w-[1400px] px-4 pb-24 pt-16 sm:px-7" aria-busy="true">
      <Skeleton className="mb-6 h-9 w-64" />
      <ContentGridSkeleton />
    </div>
  );
}
