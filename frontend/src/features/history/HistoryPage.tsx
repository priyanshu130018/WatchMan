import { Link } from "@tanstack/react-router";
import { History as HistoryIcon } from "lucide-react";
import { useAuthStore } from "@/store/authStore";
import { useClearHistory, useHistory } from "@/hooks/useMovies";
import { MovieGrid } from "@/components/movie/MovieGrid";
import { EmptyState } from "@/components/common/EmptyState";
import { Button } from "@/components/ui/button";

export function HistoryPage() {
  const isAuthed = Boolean(useAuthStore((s) => s.token));
  const { data, isLoading, isError, refetch } = useHistory();
  const clear = useClearHistory();

  if (!isAuthed) {
    return (
      <div className="mx-auto max-w-2xl px-4 py-20">
        <EmptyState
          title="Sign in to view history"
          icon={<HistoryIcon className="h-10 w-10" />}
          action={
            <Link to="/login">
              <Button className="gradient-rabbit border-0">Sign In</Button>
            </Link>
          }
        />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-black">Viewing History</h1>
          <p className="text-sm text-muted-foreground">
            Movies you've recently viewed
          </p>
        </div>
        {data && data.length > 0 && (
          <Button
            variant="secondary"
            onClick={() => clear.mutate()}
            disabled={clear.isPending}
          >
            Clear History
          </Button>
        )}
      </div>

      {data && data.length === 0 ? (
        <EmptyState
          title="Nothing viewed yet"
          description="Movies you open will show up here."
          icon={<HistoryIcon className="h-10 w-10" />}
        />
      ) : (
        <MovieGrid
          movies={data}
          loading={isLoading}
          error={isError}
          onRetry={() => refetch()}
          columns={4}
        />
      )}
    </div>
  );
}
