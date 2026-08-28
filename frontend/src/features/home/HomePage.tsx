import { useState } from "react";
import { useHome } from "@/hooks/useMovies";
import { HeroBanner } from "@/components/movie/HeroBanner";
import { MovieRow } from "@/components/movie/MovieRow";
import { RecommendationGrid } from "@/components/recommendation/RecommendationGrid";
import { MovieGrid } from "@/components/movie/MovieGrid";
import { Button } from "@/components/ui/button";
import { ChevronLeft, ChevronRight } from "lucide-react";

const PAGE_SIZE = 12;

export function HomePage() {
  const { data, isLoading, isError, refetch } = useHome();
  const [page, setPage] = useState(1);

  const recs = data?.recommendations ?? [];
  const totalPages = Math.max(1, Math.ceil(recs.length / PAGE_SIZE));
  const paged = recs.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);

  return (
    <div className="mx-auto max-w-7xl px-4 py-6 sm:px-6">
      <HeroBanner movies={data?.featured} loading={isLoading} />

      <section className="mb-10">
        <div className="mb-4 flex items-end justify-between gap-4">
          <h2 className="text-xl font-bold tracking-tight sm:text-2xl">
            <span className="text-gradient-rabbit">Rabbit</span> Recommendations
          </h2>
          <p className="text-sm text-muted-foreground">
            AI-personalized picks for you
          </p>
        </div>
        <RecommendationGrid
          movies={paged.length ? paged : recs}
          loading={isLoading}
          error={isError}
          onRetry={() => refetch()}
        />
        {recs.length > PAGE_SIZE && (
          <Pagination
            page={page}
            totalPages={totalPages}
            onChange={setPage}
          />
        )}
      </section>

      <section className="mb-10">
        <h2 className="mb-4 text-xl font-bold tracking-tight sm:text-2xl">
          Trending
        </h2>
        <MovieGrid
          movies={data?.trending?.slice(0, 10)}
          loading={isLoading}
          error={isError}
          onRetry={() => refetch()}
          columns={5}
          skeletonCount={10}
          ranked
        />
      </section>

      <section className="mb-10">
        <h2 className="mb-4 text-xl font-bold tracking-tight sm:text-2xl">
          Latest Movies & Web Series
        </h2>
        <MovieGrid
          movies={data?.latest?.slice(0, 12)}
          loading={isLoading}
          error={isError}
          onRetry={() => refetch()}
        />
      </section>

      <MovieRow title="Best on Netflix" movies={data?.netflix} loading={isLoading} error={isError} onRetry={() => refetch()} />
      <MovieRow title="Best on Prime Video" movies={data?.prime} loading={isLoading} error={isError} onRetry={() => refetch()} />
      <MovieRow title="Best on Disney+" movies={data?.disney} loading={isLoading} error={isError} onRetry={() => refetch()} />
      <MovieRow title="Best on JioHotstar" movies={data?.hotstar} loading={isLoading} error={isError} onRetry={() => refetch()} />
      <MovieRow title="Top Rated" movies={data?.top_rated} loading={isLoading} error={isError} onRetry={() => refetch()} />
    </div>
  );
}

function Pagination({
  page,
  totalPages,
  onChange,
}: {
  page: number;
  totalPages: number;
  onChange: (p: number) => void;
}) {
  const pages = Array.from({ length: totalPages }, (_, i) => i + 1);
  return (
    <div className="mt-6 flex items-center justify-center gap-2">
      <Button
        variant="secondary"
        size="sm"
        disabled={page === 1}
        onClick={() => onChange(page - 1)}
      >
        <ChevronLeft className="h-4 w-4" /> Previous
      </Button>
      {pages.map((p) => (
        <button
          key={p}
          onClick={() => onChange(p)}
          className={`h-9 min-w-9 rounded-full px-3 text-sm font-semibold transition ${
            p === page
              ? "gradient-rabbit text-white"
              : "bg-white/5 text-muted-foreground hover:bg-white/10"
          }`}
        >
          {p}
        </button>
      ))}
      <Button
        variant="secondary"
        size="sm"
        disabled={page === totalPages}
        onClick={() => onChange(page + 1)}
      >
        Next <ChevronRight className="h-4 w-4" />
      </Button>
    </div>
  );
}
