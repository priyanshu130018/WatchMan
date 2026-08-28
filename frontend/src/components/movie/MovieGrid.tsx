import type { Movie } from "@/types/movie";
import { MovieCard } from "./MovieCard";
import { MovieCardSkeleton } from "@/components/common/Skeleton";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";

export function MovieGrid({
  movies,
  loading,
  error,
  onRetry,
  columns = 4,
  skeletonCount = 12,
  ranked,
}: {
  movies?: Movie[];
  loading?: boolean;
  error?: boolean;
  onRetry?: () => void;
  columns?: 4 | 5;
  skeletonCount?: number;
  ranked?: boolean;
}) {
  const cols =
    columns === 5
      ? "grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5"
      : "grid-cols-2 sm:grid-cols-3 md:grid-cols-4";

  if (loading) {
    return (
      <div className={`grid gap-4 ${cols}`}>
        {Array.from({ length: skeletonCount }).map((_, i) => (
          <MovieCardSkeleton key={i} />
        ))}
      </div>
    );
  }
  if (error) return <ErrorState onRetry={onRetry} />;
  if (!movies || movies.length === 0)
    return <EmptyState title="No titles found" />;

  return (
    <div className={`grid gap-4 ${cols}`}>
      {movies.map((m, i) => (
        <MovieCard
          key={m.id}
          movie={m}
          showRank={ranked ? i + 1 : undefined}
        />
      ))}
    </div>
  );
}
