import React, { useState, useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { useNavigate, useSearch } from "@tanstack/react-router";
import { Search as SearchIcon, X, Film, Tv, Filter, RotateCcw } from "lucide-react";

import { ContentCard } from "@/components/ContentCard";
import { ContentGridSkeleton } from "@/components/Skeletons";
import { EmptyState, ErrorState } from "@/components/States";
import { Pagination } from "@/components/Pagination";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { catalogService, LANGUAGES, MOVIE_GENRES, TV_GENRES } from "@/services/catalog";
import { CONTENT_PAGE_SIZE } from "@/lib/constants";
import { cn } from "@/lib/utils";

const selectClass =
  "h-9 w-full rounded-md border border-border bg-secondary px-3 text-sm text-foreground outline-none transition-colors focus-visible:ring-2 focus-visible:ring-ring";

const SORT_OPTIONS = [
  { value: "popularity_desc", label: "Most popular" },
  { value: "vote_average_desc", label: "Highest rated" },
  { value: "release_date_desc", label: "Newest first" },
  { value: "release_date_asc", label: "Oldest first" },
] as const;

interface DraftSearchFilters {
  query: string;
  type: "all" | "movie" | "tv";
  genre_id?: number;
  language: string;
  year?: number;
  sort: string;
}

export function SearchPage() {
  const params = useSearch({ strict: false }) as {
    q?: string;
    type?: "all" | "movie" | "tv";
    genre_id?: string | number;
    genre?: string | number;
    language?: string;
    year?: string | number;
    sort?: string;
    page?: string | number;
  };

  const navigate = useNavigate();

  // --- APPLIED state: directly derived from URL params (Single Source of Truth) ---
  const appliedQuery = (params.q || "").trim();
  const appliedType = (params.type || "all") as "all" | "movie" | "tv";
  const rawGenre = params.genre_id ?? params.genre;
  const appliedGenreId = rawGenre ? Number(rawGenre) : undefined;
  const appliedLanguage = params.language || "";
  const appliedYear = params.year ? Number(params.year) : undefined;
  const appliedSort = params.sort || "popularity_desc";
  const appliedPage = Math.max(1, Number(params.page) || 1);

  // --- DRAFT state: local editing state. Changing this DOES NOT fetch or update URL ---
  const [draft, setDraft] = useState<DraftSearchFilters>({
    query: appliedQuery,
    type: appliedType,
    genre_id: appliedGenreId,
    language: appliedLanguage,
    year: appliedYear,
    sort: appliedSort,
  });

  // Keep draft in sync when URL parameters change externally (e.g., Browser Back/Forward, global search bar)
  useEffect(() => {
    setDraft({
      query: appliedQuery,
      type: appliedType,
      genre_id: appliedGenreId,
      language: appliedLanguage,
      year: appliedYear,
      sort: appliedSort,
    });
  }, [appliedQuery, appliedType, appliedGenreId, appliedLanguage, appliedYear, appliedSort]);

  const updateDraft = (patch: Partial<DraftSearchFilters>) => {
    setDraft((prev) => ({ ...prev, ...patch }));
  };

  // Check if draft has unapplied modifications
  const isDraftDirty =
    draft.query.trim() !== appliedQuery ||
    draft.type !== appliedType ||
    draft.genre_id !== appliedGenreId ||
    draft.language !== appliedLanguage ||
    draft.year !== appliedYear ||
    draft.sort !== appliedSort;

  // Build clean search URL object
  const buildSearchUrlParams = (
    filters: DraftSearchFilters,
    page?: number,
  ): Record<string, any> => {
    const next: Record<string, any> = {};
    const qTrimmed = filters.query.trim();
    if (qTrimmed) next.q = qTrimmed;
    if (filters.type && filters.type !== "all") next.type = filters.type;
    if (filters.genre_id) next.genre_id = filters.genre_id;
    if (filters.language) next.language = filters.language;
    if (filters.year) next.year = filters.year;
    if (filters.sort && filters.sort !== "popularity_desc") next.sort = filters.sort;
    if (page && page > 1) next.page = page;
    return next;
  };

  // COMMIT action: apply draft to URL, reset page to 1, triggers ONE API request
  const handleApply = (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    const searchParams = buildSearchUrlParams(draft, 1);
    void navigate({ to: "/search", search: searchParams as any });
  };

  // RESET / CLEAR action:
  // - resets local draft to blank defaults
  // - if applied filters exist, clears them from the URL and resets page to 1
  const handleClear = () => {
    const blankDraft: DraftSearchFilters = {
      query: "",
      type: "all",
      genre_id: undefined,
      language: "",
      year: undefined,
      sort: "popularity_desc",
    };
    setDraft(blankDraft);
    if (hasAppliedFilters) {
      void navigate({ to: "/search", search: {} as any });
    }
  };

  // Remove an individual applied filter chip
  const removeAppliedFilter = (key: keyof DraftSearchFilters) => {
    const updated = {
      query: key === "query" ? "" : appliedQuery,
      type: key === "type" ? ("all" as const) : appliedType,
      genre_id: key === "genre_id" ? undefined : appliedGenreId,
      language: key === "language" ? "" : appliedLanguage,
      year: key === "year" ? undefined : appliedYear,
      sort: key === "sort" ? "popularity_desc" : appliedSort,
    };
    setDraft(updated);
    const searchParams = buildSearchUrlParams(updated, 1);
    void navigate({ to: "/search", search: searchParams as any });
  };

  // Pagination maintains applied filters and only changes the page
  const goToPage = (nextPage: number) => {
    const appliedAsDraft: DraftSearchFilters = {
      query: appliedQuery,
      type: appliedType,
      genre_id: appliedGenreId,
      language: appliedLanguage,
      year: appliedYear,
      sort: appliedSort,
    };
    const searchParams = buildSearchUrlParams(appliedAsDraft, nextPage);
    void navigate({ to: "/search", search: searchParams as any });
  };

  // Data query: strictly keyed on APPLIED filters (draft state is NEVER in query key)
  const hasAppliedFilters = Boolean(
    appliedQuery ||
    appliedGenreId ||
    appliedLanguage ||
    appliedYear ||
    appliedType !== "all" ||
    appliedSort !== "popularity_desc",
  );

  const { data, isLoading, isError, error, refetch, isFetching } = useQuery({
    queryKey: [
      "catalogSearch",
      appliedQuery,
      appliedType,
      appliedGenreId,
      appliedLanguage,
      appliedYear,
      appliedSort,
      appliedPage,
    ],
    queryFn: () =>
      catalogService.search({
        q: appliedQuery,
        type: appliedType,
        genre_id: appliedGenreId,
        language: appliedLanguage || undefined,
        year: appliedYear,
        sort: appliedSort,
        page: appliedPage,
        limit: CONTENT_PAGE_SIZE,
      }),
    enabled: hasAppliedFilters,
  });

  const availableGenres =
    draft.type === "tv"
      ? TV_GENRES
      : draft.type === "movie"
        ? MOVIE_GENRES
        : Array.from(new Map([...MOVIE_GENRES, ...TV_GENRES].map((g) => [g.id, g])).values());

  const currentYears = Array.from({ length: 35 }, (_, i) => new Date().getFullYear() - i);

  const typeTabs: { key: "all" | "movie" | "tv"; label: string; icon?: React.ReactNode }[] = [
    { key: "all", label: "All Content" },
    { key: "movie", label: "Movies", icon: <Film size={13} aria-hidden="true" /> },
    { key: "tv", label: "Web Series", icon: <Tv size={13} aria-hidden="true" /> },
  ];

  const appliedGenreName =
    appliedGenreId !== undefined
      ? [...MOVIE_GENRES, ...TV_GENRES].find((g) => g.id === appliedGenreId)?.name ||
        `Genre ${appliedGenreId}`
      : undefined;

  const appliedLanguageName = appliedLanguage
    ? LANGUAGES.find((l) => l.code === appliedLanguage)?.name || appliedLanguage.toUpperCase()
    : undefined;

  const appliedSortLabel =
    appliedSort !== "popularity_desc"
      ? SORT_OPTIONS.find((s) => s.value === appliedSort)?.label
      : undefined;

  return (
    <div className="mx-auto max-w-[1400px] px-4 py-8 sm:px-7">
      <header className="mb-6">
        <span className="text-[11px] font-extrabold uppercase tracking-[0.16em] text-primary/80">
          Discover
        </span>
        <h1 className="mt-1 text-3xl font-bold tracking-tight text-foreground sm:text-4xl">
          Advanced Search
        </h1>
        <p className="mt-2 max-w-2xl text-sm text-muted-foreground">
          Search by title and refine results by content type, genre, language, year, or ranking.
        </p>
      </header>

      {/* Search form — submits draft values via handleApply */}
      <form onSubmit={handleApply} role="search" className="mb-5">
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
            value={draft.query}
            onChange={(e) => updateDraft({ query: e.target.value })}
            placeholder="Search by title…"
            className="h-12 pl-11 pr-24 text-base"
            autoComplete="off"
          />
          {draft.query && (
            <button
              type="button"
              onClick={() => updateDraft({ query: "" })}
              className="absolute right-[5.5rem] top-1/2 -translate-y-1/2 rounded-md p-1 text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              aria-label="Clear search text"
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

      {/* Content Type Tabs — modifies DRAFT only */}
      <div role="tablist" aria-label="Content type" className="mb-5 flex flex-wrap gap-2">
        {typeTabs.map((tab) => {
          const active = draft.type === tab.key;
          return (
            <button
              key={tab.key}
              type="button"
              role="tab"
              aria-selected={active}
              onClick={() => updateDraft({ type: tab.key })}
              className={cn(
                "inline-flex items-center gap-1.5 rounded-full border px-4 py-1.5 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring cursor-pointer",
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

      {/* Advanced Filters Panel with Local Draft State */}
      <div className="mb-8 rounded-xl border border-border bg-card p-4 sm:p-5 shadow-sm">
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <Filter size={16} className="text-primary" aria-hidden="true" />
            <h2 className="text-sm font-semibold text-foreground">Refine your search</h2>
            {isDraftDirty && (
              <span className="rounded-full bg-primary/20 px-2 py-0.5 text-[11px] font-semibold text-primary">
                Unapplied changes
              </span>
            )}
          </div>
        </div>

        {/* Filter controls — modify local draft only */}
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <div>
            <label
              htmlFor="genre-select"
              className="mb-1.5 block text-xs font-medium text-muted-foreground"
            >
              Genre
            </label>
            <select
              id="genre-select"
              className={selectClass}
              value={draft.genre_id ?? ""}
              onChange={(e) =>
                updateDraft({
                  genre_id: e.target.value ? Number(e.target.value) : undefined,
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

          <div>
            <label
              htmlFor="language-select"
              className="mb-1.5 block text-xs font-medium text-muted-foreground"
            >
              Language
            </label>
            <select
              id="language-select"
              className={selectClass}
              value={draft.language}
              onChange={(e) => updateDraft({ language: e.target.value })}
            >
              <option value="">Any language</option>
              {LANGUAGES.map((l) => (
                <option key={l.code} value={l.code}>
                  {l.name}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label
              htmlFor="year-select"
              className="mb-1.5 block text-xs font-medium text-muted-foreground"
            >
              Year
            </label>
            <select
              id="year-select"
              className={selectClass}
              value={draft.year ?? ""}
              onChange={(e) =>
                updateDraft({
                  year: e.target.value ? Number(e.target.value) : undefined,
                })
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

          <div>
            <label
              htmlFor="sort-select"
              className="mb-1.5 block text-xs font-medium text-muted-foreground"
            >
              Sort
            </label>
            <select
              id="sort-select"
              className={selectClass}
              value={draft.sort}
              onChange={(e) => updateDraft({ sort: e.target.value })}
            >
              {SORT_OPTIONS.map((s) => (
                <option key={s.value} value={s.value}>
                  {s.label}
                </option>
              ))}
            </select>
          </div>
        </div>

        {/* Panel Action Bar: Clear & Apply Filters */}
        <div className="mt-5 flex flex-col-reverse gap-2 border-t border-border pt-4 sm:flex-row sm:items-center sm:justify-between">
          <Button
            type="button"
            variant="ghost"
            onClick={handleClear}
            className="gap-2 sm:w-auto text-muted-foreground hover:text-foreground"
          >
            <RotateCcw size={15} aria-hidden="true" /> Clear
          </Button>

          <Button
            type="button"
            variant="brand"
            onClick={() => handleApply()}
            className="font-bold sm:w-auto"
          >
            Apply Filters
          </Button>
        </div>
      </div>

      {/* Applied Filters Active Chips */}
      {hasAppliedFilters && (
        <div className="mb-6 flex flex-wrap items-center gap-2">
          <span className="text-xs font-medium text-muted-foreground">Active filters:</span>
          {appliedQuery && (
            <span className="inline-flex items-center gap-1 rounded-md border border-border bg-secondary px-2.5 py-1 text-xs text-foreground">
              Query: “{appliedQuery}”
              <button
                type="button"
                onClick={() => removeAppliedFilter("query")}
                className="hover:text-destructive transition-colors ml-1"
                aria-label="Remove query filter"
              >
                <X size={12} />
              </button>
            </span>
          )}
          {appliedType !== "all" && (
            <span className="inline-flex items-center gap-1 rounded-md border border-border bg-secondary px-2.5 py-1 text-xs text-foreground">
              Type: {appliedType === "movie" ? "Movies" : "Web Series"}
              <button
                type="button"
                onClick={() => removeAppliedFilter("type")}
                className="hover:text-destructive transition-colors ml-1"
                aria-label="Remove type filter"
              >
                <X size={12} />
              </button>
            </span>
          )}
          {appliedGenreName && (
            <span className="inline-flex items-center gap-1 rounded-md border border-border bg-secondary px-2.5 py-1 text-xs text-foreground">
              Genre: {appliedGenreName}
              <button
                type="button"
                onClick={() => removeAppliedFilter("genre_id")}
                className="hover:text-destructive transition-colors ml-1"
                aria-label="Remove genre filter"
              >
                <X size={12} />
              </button>
            </span>
          )}
          {appliedLanguageName && (
            <span className="inline-flex items-center gap-1 rounded-md border border-border bg-secondary px-2.5 py-1 text-xs text-foreground">
              Language: {appliedLanguageName}
              <button
                type="button"
                onClick={() => removeAppliedFilter("language")}
                className="hover:text-destructive transition-colors ml-1"
                aria-label="Remove language filter"
              >
                <X size={12} />
              </button>
            </span>
          )}
          {appliedYear && (
            <span className="inline-flex items-center gap-1 rounded-md border border-border bg-secondary px-2.5 py-1 text-xs text-foreground">
              Year: {appliedYear}
              <button
                type="button"
                onClick={() => removeAppliedFilter("year")}
                className="hover:text-destructive transition-colors ml-1"
                aria-label="Remove year filter"
              >
                <X size={12} />
              </button>
            </span>
          )}
          {appliedSortLabel && (
            <span className="inline-flex items-center gap-1 rounded-md border border-border bg-secondary px-2.5 py-1 text-xs text-foreground">
              Sort: {appliedSortLabel}
              <button
                type="button"
                onClick={() => removeAppliedFilter("sort")}
                className="hover:text-destructive transition-colors ml-1"
                aria-label="Remove sort filter"
              >
                <X size={12} />
              </button>
            </span>
          )}
        </div>
      )}

      {/* Results Area */}
      {hasAppliedFilters ? (
        isLoading ? (
          <ContentGridSkeleton count={CONTENT_PAGE_SIZE} />
        ) : isError ? (
          <ErrorState error={error} onRetry={() => void refetch()} />
        ) : !data || data.results.length === 0 ? (
          <EmptyState
            title="No results found"
            description="No titles match your current search and filter combination. Try adjusting or clearing your filters."
            action={
              <Button variant="outline" onClick={handleClear}>
                Reset All Filters
              </Button>
            }
          />
        ) : (
          <>
            <div
              className="mb-4 flex items-center justify-between"
              role="status"
              aria-live="polite"
            >
              <p className="text-sm text-muted-foreground">
                <span className="font-semibold text-foreground">
                  {data.total ?? data.results.length}
                </span>{" "}
                result{(data.total ?? data.results.length) === 1 ? "" : "s"}
                {appliedQuery ? (
                  <>
                    {" "}
                    for <span className="font-medium text-foreground">“{appliedQuery}”</span>
                  </>
                ) : null}
              </p>
            </div>

            <ul
              className={cn(
                "grid grid-cols-2 gap-4 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6",
                isFetching && "opacity-60 transition-opacity",
              )}
            >
              {data.results.map((item) => (
                <li key={`${item.content_type || appliedType}-${item.tmdb_id || item.id}`}>
                  <ContentCard content={item} />
                </li>
              ))}
            </ul>

            {data.total_pages && data.total_pages > 1 && (
              <div className="mt-10">
                <Pagination
                  page={appliedPage}
                  totalPages={Math.min(data.total_pages, 500)}
                  onPageChange={(p) => {
                    goToPage(p);
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
