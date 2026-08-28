import { Link } from "@tanstack/react-router";
import { Heart, Search as SearchIcon } from "lucide-react";
import { useMemo, useState } from "react";
import { useAuthStore } from "@/store/authStore";
import { useFavorites } from "@/hooks/useMovies";
import { MovieGrid } from "@/components/movie/MovieGrid";
import { EmptyState } from "@/components/common/EmptyState";
import { Button } from "@/components/ui/button";

export function FavoritesPage() {
  const isAuthed = Boolean(useAuthStore((s) => s.token));
  const { data, isLoading, isError, refetch } = useFavorites();
  const [q, setQ] = useState("");

  const filtered = useMemo(() => {
    if (!data) return data;
    if (!q.trim()) return data;
    const needle = q.toLowerCase();
    return data.filter((m) => m.title.toLowerCase().includes(needle));
  }, [data, q]);

  if (!isAuthed) {
    return (
      <div className="mx-auto max-w-2xl px-4 py-20">
        <EmptyState
          title="Sign in to see your favorites"
          description="Your favorite movies sync across devices."
          icon={<Heart className="h-10 w-10" />}
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
      <div className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-black">Favorites</h1>
          <p className="text-sm text-muted-foreground">
            {data?.length ?? 0} saved
          </p>
        </div>
        <div className="relative w-full sm:w-72">
          <SearchIcon className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search favorites"
            className="w-full rounded-full border border-white/10 bg-white/5 py-2 pl-10 pr-3 text-sm focus:outline-none focus:ring-2 focus:ring-primary/60"
          />
        </div>
      </div>

      {data && data.length === 0 ? (
        <EmptyState
          title="No favorites yet"
          description="Tap the heart on any movie to save it here."
          icon={<Heart className="h-10 w-10" />}
        />
      ) : (
        <MovieGrid
          movies={filtered}
          loading={isLoading}
          error={isError}
          onRetry={() => refetch()}
          columns={4}
        />
      )}
    </div>
  );
}
