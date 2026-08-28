import { Link } from "@tanstack/react-router";
import { ChevronRight } from "lucide-react";
import type { Movie } from "@/types/movie";
import { MovieCard } from "./MovieCard";
import { RowSkeleton } from "@/components/common/Skeleton";
import { ErrorState } from "@/components/common/ErrorState";
import { EmptyState } from "@/components/common/EmptyState";

interface Props {
  title: string;
  movies?: Movie[];
  loading?: boolean;
  error?: boolean;
  onRetry?: () => void;
  viewMoreTo?: string;
  ranked?: boolean;
}

export function MovieRow({
  title,
  movies,
  loading,
  error,
  onRetry,
  viewMoreTo,
  ranked,
}: Props) {
  return (
    <section className="mb-10">
      <div className="mb-4 flex items-end justify-between gap-4">
        <h2 className="text-xl font-bold tracking-tight sm:text-2xl">{title}</h2>
        {viewMoreTo && (
          <Link
            to={viewMoreTo}
            className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground transition"
          >
            View more <ChevronRight className="h-4 w-4" />
          </Link>
        )}
      </div>

      {loading ? (
        <RowSkeleton />
      ) : error ? (
        <ErrorState onRetry={onRetry} />
      ) : !movies || movies.length === 0 ? (
        <EmptyState title="No titles yet" />
      ) : (
        <div className="flex snap-x snap-mandatory gap-4 overflow-x-auto pb-3 scrollbar-hide">
          {movies.map((m, i) => (
            <div
              key={m.id}
              className="w-40 shrink-0 snap-start sm:w-48"
            >
              <MovieCard movie={m} showRank={ranked ? i + 1 : undefined} />
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
