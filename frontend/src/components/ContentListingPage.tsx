import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ChevronDown, Filter, RotateCcw } from "lucide-react";

import { ContentCard } from "./ContentCard";
import { ContentGridSkeleton } from "./Skeletons";
import { Pagination } from "./Pagination";
import { EmptyState, ErrorState } from "./States";
import { Button } from "@/components/ui/button";
import {
  catalogService,
  MOVIE_GENRES,
  TV_GENRES,
  LANGUAGES,
  type CatalogFilterParams,
} from "@/services/catalog";
import { CONTENT_PAGE_SIZE, POPULAR_COLLECTION_MAX } from "@/lib/constants";
import { type ContentType } from "@/types/content";
import { cn } from "@/lib/utils";

const DEFAULT_SORT = "popularity_desc";

/** Sort values the backend catalog repository understands (see content_repository). */
const SORT_OPTIONS = [
  { value: "popularity_desc", label: "Most Popular" },
  { value: "vote_average_desc", label: "Top Rated" },
  { value: "release_date_desc", label: "Newest First" },
  { value: "release_date_asc", label: "Oldest First" },
] as const;

const selectClass =
  "h-9 w-full rounded-md border border-border bg-secondary px-3 text-sm text-foreground outline-none transition-colors focus-visible:ring-2 focus-visible:ring-ring";

export interface ListingFilters {
  page?: number;
  genre?: number;
  genre_id?: number;
  year?: number;
  language?: string;
  sort?: string;
  /** `"popular"` = top {@link POPULAR_COLLECTION_MAX} by popularity; omitted = full catalogue. */
  collection?: string;
}

/** Draft = what the user is editing in the (open) panel. Never drives fetching. */
interface DraftFilters {
  genre?: number;
  year?: number;
  language?: string;
  sort: string;
}

export interface ContentListingPageProps {
  title: string;
  subtitle?: string;
  contentType: ContentType;
  searchParams: ListingFilters;
  onUpdateFilters: (filters: ListingFilters) => void;
}
import { getContentListingQueryKey } from "@/lib/catalogHelpers";
export { getContentListingQueryKey };

export function ContentListingPage({
  title,
  subtitle,
  contentType,
  searchParams,
  onUpdateFilters,
}: ContentListingPageProps) {
  // --- APPLIED filters: derived purely from the URL (the source of truth). ---
  // These are the only values that feed the data query, so changing draft state
  // in the panel can never trigger a fetch.
  const page = Number(searchParams.page) > 1 ? Number(searchParams.page) : 1;
  const rawGenre = searchParams.genre ?? searchParams.genre_id;
  const genreId = rawGenre ? Number(rawGenre) : undefined;
  const year = searchParams.year ? Number(searchParams.year) : undefined;
  const language = searchParams.language || undefined;
  // In the popular collection the backend forces popularity ordering, so the
  // applied sort is pinned to the default there (no user sort in popular mode).
  const collection = searchParams.collection === "popular" ? "popular" : undefined;
  const isPopular = collection === "popular";
  const sort = isPopular ? DEFAULT_SORT : searchParams.sort || DEFAULT_SORT;

  const genres = contentType === "movie" ? MOVIE_GENRES : TV_GENRES;

  // --- DRAFT filters: local-only panel state. Never referenced by the query. ---
  const [panelOpen, setPanelOpen] = useState(false);
  const [draft, setDraft] = useState<DraftFilters>({ genre: genreId, year, language, sort });

  // --- Data query: keyed ONLY on applied (URL-derived) values. ---
  const activeMode = collection === "popular" ? "popular" : "all";
  const { data, isLoading, isError, error, refetch, isFetching } = useQuery({
    queryKey: getContentListingQueryKey(contentType, collection, {
      page,
      genreId,
      year,
      language,
      sort,
    }),
    queryFn: () => {
      const params: CatalogFilterParams = {
        page,
        limit: CONTENT_PAGE_SIZE,
        sort,
        year,
        genre_id: genreId,
        language,
        collection,
      };
      return contentType === "movie"
        ? catalogService.getMovies(params)
        : catalogService.getWebSeries(params);
    },
    // Keep previous page data during page navigation, but NEVER when mode or filter criteria change
    placeholderData: (previousData, previousQuery) => {
      const prevKey = previousQuery?.queryKey;
      if (!prevKey) return undefined;
      const prevMode = prevKey[2];
      if (prevMode !== activeMode) {
        return undefined;
      }
      const prevFilters = prevKey[3] as any;
      if (
        prevFilters?.genreId !== genreId ||
        prevFilters?.year !== year ||
        prevFilters?.language !== language ||
        prevFilters?.sort !== sort
      ) {
        return undefined;
      }
      return previousData;
    },
    staleTime: 30_000,
  });
  // Only emit params that are actually selected — no empty/default keys.
  // (undefined values are dropped from the URL by the router.)
  const buildSearch = (f: {
    genre?: number;
    year?: number;
    language?: string;
    sort?: string;
    page?: number;
    collection?: string;
  }): ListingFilters => {
    const next: ListingFilters = {};
    if (f.genre) next.genre = f.genre;
    if (f.year) next.year = f.year;
    if (f.language) next.language = f.language;
    if (f.collection === "popular") {
      // Popular is popularity-ordered server-side; carry the collection, not sort.
      next.collection = "popular";
    } else if (f.sort && f.sort !== DEFAULT_SORT) {
      next.sort = f.sort;
    }
    if (f.page && f.page > 1) next.page = f.page;
    return next;
  };

  const updateDraft = (patch: Partial<DraftFilters>) => setDraft((prev) => ({ ...prev, ...patch }));

  // Opening seeds the draft from the currently applied (URL) filters.
  const openPanel = () => {
    setDraft({ genre: genreId, year, language, sort });
    setPanelOpen(true);
  };
  // Closing without Apply simply discards the draft; applied state is untouched.
  const closePanel = () => setPanelOpen(false);
  // Reset only clears the DRAFT — it does not fetch or touch the URL.
  const resetDraft = () =>
    setDraft({ genre: undefined, year: undefined, language: undefined, sort: DEFAULT_SORT });

  // The single place that commits filters: updates the URL (→ query refetches once)
  // and resets pagination to page 1. Collection is preserved (toggle owns it).
  const applyDraft = () => {
    onUpdateFilters(buildSearch({ ...draft, page: 1, collection }));
    setPanelOpen(false);
  };

  // Pagination keeps the applied filters (and collection) and only changes the page.
  const goToPage = (nextPage: number) =>
    onUpdateFilters(
      buildSearch({ genre: genreId, year, language, sort, page: nextPage, collection }),
    );

  // Collection toggle: switches Full Catalogue <-> Popular, resetting to page 1.
  // Genre/year/language filters are preserved across the switch.
  const selectCollection = (nextCollection: "popular" | undefined) => {
    if (nextCollection === collection) return;
    onUpdateFilters(
      buildSearch({ genre: genreId, year, language, sort, page: 1, collection: nextCollection }),
    );
    setPanelOpen(false);
  };

  // Clears applied filters entirely (empty URL → default dataset).
  const clearAppliedFilters = () => {
    onUpdateFilters({});
    setPanelOpen(false);
  };

  const currentYear = new Date().getFullYear();
  const yearOptions = Array.from({ length: currentYear - 1949 }, (_, i) => currentYear - i);

  const activeFilterCount =
    (genreId ? 1 : 0) +
    (year ? 1 : 0) +
    (language ? 1 : 0) +
    (!isPopular && sort !== DEFAULT_SORT ? 1 : 0);
  const hasActiveFilters = activeFilterCount > 0;
  return (
    <div className="mx-auto max-w-[1400px] px-4 pb-24 pt-10 sm:px-7">
      {/* Header */}
      <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
        <div className="min-w-0">
          {subtitle && (
            <p className="text-xs font-semibold uppercase tracking-wider text-primary">
              {subtitle}
            </p>
          )}
          <h1 className="text-2xl font-bold tracking-tight text-foreground sm:text-3xl">{title}</h1>
          {isPopular && (
            <p className="mt-1 text-sm text-muted-foreground">
              Top {data ? Math.min(data.total, POPULAR_COLLECTION_MAX) : POPULAR_COLLECTION_MAX} by
              popularity
            </p>
          )}
        </div>

        <div className="flex flex-wrap items-center gap-3">
          {/* Collection toggle — Full Catalogue vs. Popular (top 100). */}
          <div
            role="tablist"
            aria-label="Collection"
            className="inline-flex rounded-lg border border-border bg-secondary p-0.5"
          >
            <button
              type="button"
              role="tab"
              aria-selected={!isPopular}
              onClick={() => selectCollection(undefined)}
              className={cn(
                "rounded-md px-3 py-1.5 text-sm font-medium transition-colors",
                !isPopular
                  ? "bg-brand-gradient text-watchman-black"
                  : "text-muted-foreground hover:text-foreground",
              )}
            >
              Full Catalogue
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={isPopular}
              onClick={() => selectCollection("popular")}
              className={cn(
                "rounded-md px-3 py-1.5 text-sm font-medium transition-colors",
                isPopular
                  ? "bg-brand-gradient text-watchman-black"
                  : "text-muted-foreground hover:text-foreground",
              )}
            >
              Popular
            </button>
          </div>

          <Button
            variant="outline"
            onClick={() => (panelOpen ? closePanel() : openPanel())}
            aria-expanded={panelOpen}
            aria-controls="filter-panel"
            className="gap-2"
          >
            <Filter size={16} aria-hidden="true" />
            Filters
            {activeFilterCount > 0 && (
              <span className="inline-flex h-5 min-w-5 items-center justify-center rounded-full bg-brand-gradient px-1.5 text-[11px] font-bold text-watchman-black">
                {activeFilterCount}
              </span>
            )}
            <ChevronDown
              size={16}
              aria-hidden="true"
              className={cn("transition-transform duration-200", panelOpen && "rotate-180")}
            />
          </Button>
        </div>
      </div>
      {/* Filter panel — edits DRAFT state only. Nothing here fetches. */}
      {panelOpen && (
        <div id="filter-panel" className="mb-6 rounded-xl border border-border bg-card p-4 sm:p-5">
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <label className="block">
              <span className="mb-1.5 block text-xs font-medium text-muted-foreground">
                Language
              </span>
              <select
                className={selectClass}
                value={draft.language ?? ""}
                onChange={(e) => updateDraft({ language: e.target.value || undefined })}
              >
                <option value="">Any language</option>
                {LANGUAGES.map((l) => (
                  <option key={l.code} value={l.code}>
                    {l.name}
                  </option>
                ))}
              </select>
            </label>

            <label className="block">
              <span className="mb-1.5 block text-xs font-medium text-muted-foreground">Genre</span>
              <select
                className={selectClass}
                value={draft.genre ?? ""}
                onChange={(e) =>
                  updateDraft({ genre: e.target.value ? Number(e.target.value) : undefined })
                }
              >
                <option value="">Any genre</option>
                {genres.map((g) => (
                  <option key={g.id} value={g.id}>
                    {g.name}
                  </option>
                ))}
              </select>
            </label>
            <label className="block">
              <span className="mb-1.5 block text-xs font-medium text-muted-foreground">Year</span>
              <select
                className={selectClass}
                value={draft.year ?? ""}
                onChange={(e) =>
                  updateDraft({ year: e.target.value ? Number(e.target.value) : undefined })
                }
              >
                <option value="">Any year</option>
                {yearOptions.map((y) => (
                  <option key={y} value={y}>
                    {y}
                  </option>
                ))}
              </select>
            </label>

            {/* Sort is hidden in Popular mode — the backend pins popularity order there. */}
            {!isPopular && (
              <label className="block">
                <span className="mb-1.5 block text-xs font-medium text-muted-foreground">
                  Sort By
                </span>
                <select
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
              </label>
            )}
          </div>
          <div className="mt-4 flex flex-col-reverse gap-2 border-t border-border pt-4 sm:flex-row sm:items-center sm:justify-between">
            <Button variant="ghost" onClick={resetDraft} className="gap-2 sm:w-auto">
              <RotateCcw size={15} aria-hidden="true" /> Reset
            </Button>
            <div className="flex flex-col-reverse gap-2 sm:flex-row">
              <Button variant="outline" onClick={closePanel}>
                Cancel
              </Button>
              <Button variant="brand" onClick={applyDraft}>
                Apply Filters
              </Button>
            </div>
          </div>
        </div>
      )}
      {/* Results — driven entirely by APPLIED (URL) filters via the query. */}
      {isLoading ? (
        <ContentGridSkeleton count={CONTENT_PAGE_SIZE} />
      ) : isError ? (
        <ErrorState error={error} onRetry={() => void refetch()} />
      ) : !data || data.results.length === 0 ? (
        <EmptyState
          title="No titles found"
          description={
            hasActiveFilters
              ? "No results match your current filters. Try adjusting or clearing them."
              : "There's nothing to show here yet. Check back soon."
          }
          action={
            hasActiveFilters ? (
              <Button variant="outline" onClick={clearAppliedFilters}>
                Reset Filters
              </Button>
            ) : undefined
          }
        />
      ) : (
        <>
          <div
            className={cn(
              "grid grid-cols-2 gap-4 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6",
              isFetching && "opacity-60 transition-opacity",
            )}
          >
            {data.results.map((item) => (
              <ContentCard key={`${item.content_type}-${item.id}`} content={item} />
            ))}
          </div>

          {data.total_pages > 1 && (
            <div className="mt-10">
              <Pagination
                page={data.page}
                totalPages={data.total_pages}
                onPageChange={goToPage}
                disabled={isFetching}
              />
            </div>
          )}
        </>
      )}
    </div>
  );
}
