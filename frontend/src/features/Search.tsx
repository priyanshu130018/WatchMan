import React, { useState, useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { useNavigate, useSearch } from "@tanstack/react-router";
import { Search as SearchIcon, X, Film, Tv } from "lucide-react";

import { ContentCard } from "@/components/ContentCard";
import { ContentGridSkeleton } from "@/components/Skeletons";
import { EmptyState, ErrorState } from "@/components/States";
import { Pagination } from "@/components/Pagination";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { catalogService, MOVIE_GENRES, TV_GENRES } from "@/services/catalog";
import { CONTENT_PAGE_SIZE } from "@/lib/constants";
import { cn } from "@/lib/utils";

const selectClass =
  "h-9 rounded-md border border-border bg-secondary px-3 text-sm text-foreground outline-none transition-colors focus-visible:ring-2 focus-visible:ring-ring";

export function SearchPage() {
  const params = useSearch({ strict: false }) as {
    q?: string;
    type?: "all" | "movie" | "tv";
    genre_id?: string | number;
    year?: string | number;
    sort?: string;
    page?: string | number;
  };

  const navigate = useNavigate();

  const currentQuery = params.q || "";
  const currentType = (params.type || "all") as "all" | "movie" | "tv";
  const currentGenreId = params.genre_id ? Number(params.genre_id) : undefined;
  const currentYear = params.year ? Number(params.year) : undefined;
  const currentSort = params.sort || "popularity_desc";
  const currentPage = Math.max(1, Number(params.page) || 1);

  const [inputVal, setInputVal] = useState(currentQuery);

  useEffect(() => {
    setInputVal(currentQuery);
  }, [currentQuery]);

  const updateSearch = (newParams: Partial<typeof params>) => {
    const updated = {
      q: newParams.q !== undefined ? newParams.q : params.q || undefined,
      type:
        newParams.type !== undefined
          ? newParams.type === "all"
            ? undefined
            : newParams.type
          : params.type && params.type !== "all"
            ? params.type
            : undefined,
      genre_id:
        newParams.genre_id !== undefined
          ? newParams.genre_id || undefined
          : params.genre_id || undefined,
      year: newParams.year !== undefined ? newParams.year || undefined : params.year || undefined,
      sort:
        newParams.sort !== undefined
          ? newParams.sort === "popularity_desc"
            ? undefined
            : newParams.sort
          : params.sort && params.sort !== "popularity_desc"
            ? params.sort
            : undefined,
      page:
        newParams.page !== undefined
          ? Number(newParams.page) > 1
            ? newParams.page
            : undefined
          : undefined,
    };

    const cleaned: Record<string, any> = {};
    for (const [k, v] of Object.entries(updated)) {
      if (v !== undefined && v !== "") cleaned[k] = v;
    }

    void navigate({ to: "/search", search: cleaned as any });
  };

  const handleFormSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    updateSearch({ q: inputVal.trim() || undefined, page: 1 });
  };

  const handleClearInput = () => {
    setInputVal("");
    updateSearch({ q: undefined, page: 1 });
  };

  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: [
      "catalogSearch",
      currentQuery,
      currentType,
      currentGenreId,
      currentYear,
      currentSort,
      currentPage,
    ],
    queryFn: () =>
      catalogService.search({
        q: currentQuery,
        type: currentType,
        genre_id: currentGenreId,
        year: currentYear,
        sort: currentSort,
        page: currentPage,
        limit: CONTENT_PAGE_SIZE,
      }),
    enabled:
      currentQuery.trim().length > 0 || currentGenreId !== undefined || currentYear !== undefined,
    placeholderData: (prev) => prev,
  });

  const availableGenres =
    currentType === "tv"
      ? TV_GENRES
      : currentType === "movie"
        ? MOVIE_GENRES
        : Array.from(new Map([...MOVIE_GENRES, ...TV_GENRES].map((g) => [g.id, g])).values());

  const currentYears = Array.from({ length: 35 }, (_, i) => new Date().getFullYear() - i);

  const hasActiveFilters = Boolean(
    currentQuery ||
    currentGenreId ||
    currentYear ||
    currentType !== "all" ||
    currentSort !== "popularity_desc",
  );

  const typeTabs: { key: "all" | "movie" | "tv"; label: string; icon?: React.ReactNode }[] = [
    { key: "all", label: "All Content" },
    { key: "movie", label: "Movies", icon: <Film size={13} aria-hidden="true" /> },
    { key: "tv", label: "Web Series", icon: <Tv size={13} aria-hidden="true" /> },
  ];

  return (
    <div className="mx-auto max-w-[1400px] px-4 py-8 sm:px-7">
      <header className="mb-6">
        <span className="text-[11px] font-extrabold uppercase tracking-[0.16em] text-primary/80">
          Discover
        </span>
        <h1 className="mt-1 text-3xl font-bold tracking-tight text-foreground sm:text-4xl">
          Search &amp; Browse
        </h1>
        <p className="mt-2 max-w-2xl text-sm text-muted-foreground">
          Find movies and web series by title, or narrow the catalog with filters.
        </p>
      </header>

      {/* Search form */}
      <form onSubmit={handleFormSubmit} role="search" className="mb-5">
        <label htmlFor="search-input" className="sr-only">
          Search movies and web series
        </label>
        <div className="relative">
          <SearchIcon
            size={18}
            className="pointer-events-none absolute left-3.5 top-1/2 -translate-y-1/2 text-muted-foreground"
            aria-hidden="true"
          />
          <Input
            id="search-input"
            type="search"
            value={inputVal}
            onChange={(e) => setInputVal(e.target.value)}
            placeholder="Search by title…"
            className="h-12 pl-11 pr-24 text-base"
            autoComplete="off"
          />
          {inputVal && (
            <button
              type="button"
              onClick={handleClearInput}
              className="absolute right-[5.5rem] top-1/2 -translate-y-1/2 rounded-md p-1 text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              aria-label="Clear search"
            >
              <X size={16} aria-hidden="true" />
            </button>
          )}
          <Button
            type="submit"
            variant="brand"
            className="absolute right-1.5 top-1/2 -translate-y-1/2 h-9"
          >
            Search
          </Button>
        </div>
      </form>

      {/* Type tabs */}
      <div role="tablist" aria-label="Content type" className="mb-4 flex flex-wrap gap-2">
        {typeTabs.map((tab) => {
          const active = currentType === tab.key;
          return (
            <button
              key={tab.key}
              type="button"
              role="tab"
              aria-selected={active}
              onClick={() => updateSearch({ type: tab.key, genre_id: undefined, page: 1 })}
              className={cn(
                "inline-flex items-center gap-1.5 rounded-full border px-4 py-1.5 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                active
                  ? "border-transparent bg-brand-gradient text-watchman-black"
                  : "border-border bg-secondary text-muted-foreground hover:bg-accent hover:text-foreground",
              )}
            >
              {tab.icon}
              {tab.label}
            </button>
          );
        })}
      </div>

      {/* Filter bar */}
      <div className="mb-8 flex flex-wrap items-center gap-3">
        <div className="flex items-center gap-1.5">
          <label htmlFor="genre-select" className="text-xs font-medium text-muted-foreground">
            Genre
          </label>
          <select
            id="genre-select"
            className={selectClass}
            value={currentGenreId ?? ""}
            onChange={(e) =>
              updateSearch({
                genre_id: e.target.value ? Number(e.target.value) : undefined,
                page: 1,
              })
            }
          >
            <option value="">Any genre</option>
            {availableGenres.map((g) => (
              <option key={g.id} value={g.id}>
                {g.name}
              </option>
            ))}
          </select>
        </div>

        <div className="flex items-center gap-1.5">
          <label htmlFor="year-select" className="text-xs font-medium text-muted-foreground">
            Year
          </label>
          <select
            id="year-select"
            className={selectClass}
            value={currentYear ?? ""}
            onChange={(e) =>
              updateSearch({ year: e.target.value ? Number(e.target.value) : undefined, page: 1 })
            }
          >
            <option value="">Any year</option>
            {currentYears.map((y) => (
              <option key={y} value={y}>
                {y}
              </option>
            ))}
          </select>
        </div>

        <div className="flex items-center gap-1.5">
          <label htmlFor="sort-select" className="text-xs font-medium text-muted-foreground">
            Sort
          </label>
          <select
            id="sort-select"
            className={selectClass}
            value={currentSort}
            onChange={(e) => updateSearch({ sort: e.target.value, page: 1 })}
          >
            <option value="popularity_desc">Most popular</option>
            <option value="rating_desc">Highest rated</option>
            <option value="release_desc">Newest first</option>
            <option value="release_asc">Oldest first</option>
            <option value="title_asc">Title A–Z</option>
          </select>
        </div>

        {hasActiveFilters && (
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={() => {
              setInputVal("");
              void navigate({ to: "/search", search: {} as any });
            }}
            className="ml-auto"
          >
            <X size={14} aria-hidden="true" /> Clear all
          </Button>
        )}
      </div>

      {/* Results */}
      {currentQuery.trim().length > 0 ||
      currentGenreId !== undefined ||
      currentYear !== undefined ? (
        isLoading ? (
          <ContentGridSkeleton count={CONTENT_PAGE_SIZE} />
        ) : isError ? (
          <ErrorState error={error} onRetry={() => void refetch()} />
        ) : !data || data.results.length === 0 ? (
          <EmptyState
            title="No results found"
            description="Try a different title or adjust your filters."
          />
        ) : (
          <>
            <div
              className="mb-4 flex items-center justify-between"
              role="status"
              aria-live="polite"
            >
              <p className="text-sm text-muted-foreground">
                {data.total ?? data.results.length} result
                {(data.total ?? data.results.length) === 1 ? "" : "s"}
                {currentQuery ? (
                  <>
                    {" "}
                    for <span className="font-medium text-foreground">“{currentQuery}”</span>
                  </>
                ) : null}
              </p>
            </div>

            <ul className="grid grid-cols-2 gap-4 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6">
              {data.results.map((item) => (
                <li key={`${item.content_type || currentType}-${item.tmdb_id || item.id}`}>
                  <ContentCard content={item} />
                </li>
              ))}
            </ul>

            {data.total_pages && data.total_pages > 1 && (
              <div className="mt-10">
                <Pagination
                  page={currentPage}
                  totalPages={Math.min(data.total_pages, 500)}
                  onPageChange={(p) => {
                    updateSearch({ page: p });
                    window.scrollTo({ top: 0, behavior: "smooth" });
                  }}
                  disabled={isLoading}
                />
              </div>
            )}
          </>
        )
      ) : (
        <EmptyState
          title="Start exploring"
          description="Search for a title above, or pick a genre and year to browse the catalog."
        />
      )}
    </div>
  );
}
