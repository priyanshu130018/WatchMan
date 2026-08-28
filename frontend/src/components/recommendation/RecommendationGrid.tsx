import { MovieGrid } from "@/components/movie/MovieGrid";
import type { Movie } from "@/types/movie";

export function RecommendationGrid(props: {
  movies?: Movie[];
  loading?: boolean;
  error?: boolean;
  onRetry?: () => void;
}) {
  return <MovieGrid {...props} columns={4} skeletonCount={12} />;
}
