import { useQuery } from "@tanstack/react-query";
import { Film, MonitorPlay, Tv } from "lucide-react";

import { ContentCard } from "@/components/ContentCard";
import { ContentGridSkeleton } from "@/components/Skeletons";
import { Pagination } from "@/components/Pagination";
import { EmptyState, ErrorState } from "@/components/States";
import { imageUrl, type ContentType } from "@/types/content";
import { FALLBACK_OTT_REGIONS, ottService } from "@/services/ott";
import { cn } from "@/lib/utils";

const DEFAULT_REGION = "IN";

const selectClass =
  "h-9 w-full rounded-md border border-border bg-secondary px-3 text-sm text-foreground outline-none transition-colors focus-visible:ring-2 focus-visible:ring-ring";

export interface OttFilters {
  region?: string;
  type?: "movie" | "tv";
  provider?: number;
  page?: number;
}

export interface OttPageProps {
  searchParams: OttFilters;
  onUpdateFilters: (filters: OttFilters) => void;
}
export function OttPage({ searchParams, onUpdateFilters }: OttPageProps) {
  // --- Applied state derived purely from the URL (the source of truth). ---
  const region = searchParams.region || DEFAULT_REGION;
  const contentType: ContentType = searchParams.type === "tv" ? "tv" : "movie";
  const providerId = searchParams.provider ? Number(searchParams.provider) : undefined;
  const page = Number(searchParams.page) > 1 ? Number(searchParams.page) : 1;

  // Regions for the selector (falls back to a curated real-region list offline).
  const regionsQuery = useQuery({
    queryKey: ["ott", "regions"],
    queryFn: ottService.getRegions,
    staleTime: 24 * 60 * 60 * 1000,
  });
  const regions =
    regionsQuery.data && regionsQuery.data.length > 0 ? regionsQuery.data : FALLBACK_OTT_REGIONS;
  const regionName = regions.find((r) => r.iso_3166_1 === region)?.english_name || region;

  // Streaming providers available for the region + media type.
  const providersQuery = useQuery({
    queryKey: ["ott", "providers", region, contentType],
    queryFn: () => ottService.getProviders(region, contentType),
    staleTime: 60 * 60 * 1000,
  });
  const providers = providersQuery.data ?? [];
  const selectedProvider = providers.find((p) => p.provider_id === providerId);

  // Titles available on the selected provider (only fetched once one is chosen).
  const resultsQuery = useQuery({
    queryKey: ["ott", "discover", { region, contentType, providerId, page }],
    queryFn: () =>
      ottService.discoverByProvider({
        contentType,
        providerId: providerId as number,
        region,
        page,
      }),
    enabled: Boolean(providerId),
    staleTime: 30_000,
  });

  // Every commit rewrites the URL; only non-default values are emitted.
  const commit = (next: OttFilters) => {
    const clean: OttFilters = {};
    if (next.region && next.region !== DEFAULT_REGION) clean.region = next.region;
    if (next.type === "tv") clean.type = "tv";
    if (next.provider) clean.provider = next.provider;
    if (next.page && next.page > 1) clean.page = next.page;
    onUpdateFilters(clean);
  };
  // Changing region or media type invalidates the current provider selection
  // (a service in one region/type may not exist in another) → reset provider + page.
  const changeRegion = (nextRegion: string) =>
    commit({ region: nextRegion, type: searchParams.type });
  const changeType = (nextType: "movie" | "tv") => commit({ region, type: nextType });
  const selectProvider = (id: number) =>
    commit({ region, type: searchParams.type, provider: id === providerId ? undefined : id });
  const goToPage = (nextPage: number) =>
    commit({ region, type: searchParams.type, provider: providerId, page: nextPage });

  const results = resultsQuery.data;

  return (
    <div className="mx-auto max-w-[1400px] px-4 pb-24 pt-10 sm:px-7">
      {/* Header */}
      <header className="mb-6">
        <span className="inline-flex items-center gap-1.5 text-[11px] font-extrabold uppercase tracking-[0.16em] text-primary/80">
          <MonitorPlay size={14} aria-hidden="true" /> Where to Stream
        </span>
        <h1 className="mt-1 text-3xl font-bold tracking-tight text-foreground sm:text-4xl">
          OTT &amp; Streaming
        </h1>
        <p className="mt-2 max-w-2xl text-sm text-muted-foreground">
          Browse what&apos;s available on each streaming service in your region. Availability is
          reported live by JustWatch via TMDB.
        </p>
      </header>

      {/* Controls: region + media type */}
      <div className="mb-8 flex flex-wrap items-end justify-between gap-4 rounded-2xl border border-border bg-card/50 p-3">
        <label className="block w-full sm:w-56">
          <span className="mb-1.5 block text-xs font-medium text-muted-foreground">Region</span>
          <select
            className={selectClass}
            value={region}
            onChange={(e) => changeRegion(e.target.value)}
            aria-label="Streaming region"
          >
            {regions.map((r) => (
              <option key={r.iso_3166_1} value={r.iso_3166_1}>
                {r.english_name}
              </option>
            ))}
          </select>
        </label>

        <div role="group" aria-label="Content type" className="flex items-center gap-2">
          {(
            [
              ["movie", "Movies", <Film key="m" size={14} aria-hidden="true" />],
              ["tv", "Web Series", <Tv key="t" size={14} aria-hidden="true" />],
            ] as const
          ).map(([value, label, icon]) => {
            const active = contentType === value;
            return (
              <button
                key={value}
                type="button"
                aria-pressed={active}
                onClick={() => changeType(value)}
                className={cn(
                  "inline-flex items-center gap-1.5 rounded-full border px-4 py-1.5 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                  active
                    ? "border-transparent bg-brand-gradient text-white"
                    : "border-border bg-secondary text-muted-foreground hover:bg-accent hover:text-foreground",
                )}
              >
                {icon}
                {label}
              </button>
            );
          })}
        </div>
      </div>
      {/* Provider grid */}
      <section aria-labelledby="ott-providers-heading" className="mb-10">
        <h2
          id="ott-providers-heading"
          className="mb-4 text-sm font-semibold uppercase tracking-wider text-muted-foreground"
        >
          Streaming services in {regionName}
        </h2>

        {providersQuery.isLoading ? (
          <div className="grid grid-cols-3 gap-3 sm:grid-cols-5 md:grid-cols-6 lg:grid-cols-8">
            {Array.from({ length: 16 }).map((_, i) => (
              <div
                key={i}
                className="aspect-square animate-pulse rounded-xl border border-border bg-secondary"
                aria-hidden="true"
              />
            ))}
          </div>
        ) : providersQuery.isError ? (
          <ErrorState
            title="Could not load streaming services"
            error={providersQuery.error}
            onRetry={() => void providersQuery.refetch()}
          />
        ) : providers.length === 0 ? (
          <EmptyState
            icon={<MonitorPlay size={40} aria-hidden="true" />}
            title="No streaming services found"
            description={`TMDB has no ${contentType === "tv" ? "web series" : "movie"} provider data for ${regionName}. Try another region.`}
          />
        ) : (
          <ul className="grid grid-cols-3 gap-3 sm:grid-cols-5 md:grid-cols-6 lg:grid-cols-8">
            {providers.map((p) => {
              const active = p.provider_id === providerId;
              const logo = imageUrl(p.logo_path, "w185");
              return (
                <li key={p.provider_id}>
                  <button
                    type="button"
                    onClick={() => selectProvider(p.provider_id)}
                    aria-pressed={active}
                    title={p.provider_name}
                    className={cn(
                      "flex aspect-square w-full flex-col items-center justify-center gap-1.5 overflow-hidden rounded-xl border p-2 text-center transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                      active
                        ? "border-primary bg-primary/10 ring-2 ring-primary"
                        : "border-border bg-card hover:border-primary/50 hover:bg-accent",
                    )}
                  >
                    {logo ? (
                      <img
                        src={logo}
                        alt={p.provider_name}
                        loading="lazy"
                        className="h-11 w-11 rounded-lg object-cover"
                      />
                    ) : (
                      <MonitorPlay size={24} aria-hidden="true" className="text-muted-foreground" />
                    )}
                    <span className="line-clamp-2 text-[10px] font-medium leading-tight text-foreground/90">
                      {p.provider_name}
                    </span>
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </section>
      {/* Results for the selected provider */}
      <section aria-labelledby="ott-results-heading">
        {!providerId ? (
          <EmptyState
            icon={<MonitorPlay size={40} aria-hidden="true" />}
            title="Pick a streaming service"
            description={`Select a service above to browse the ${contentType === "tv" ? "web series" : "movies"} it's streaming in ${regionName}.`}
          />
        ) : (
          <>
            <h2
              id="ott-results-heading"
              className="mb-4 text-lg font-bold tracking-tight text-foreground"
            >
              {selectedProvider
                ? `Streaming on ${selectedProvider.provider_name}`
                : "Available titles"}
              <span className="ml-2 text-sm font-normal text-muted-foreground">
                in {regionName}
              </span>
            </h2>

            {resultsQuery.isLoading ? (
              <ContentGridSkeleton count={16} />
            ) : resultsQuery.isError ? (
              <ErrorState
                title="Could not load titles"
                error={resultsQuery.error}
                onRetry={() => void resultsQuery.refetch()}
              />
            ) : !results || results.results.length === 0 ? (
              <EmptyState
                title="Nothing available here"
                description={`TMDB reports no ${contentType === "tv" ? "web series" : "movies"} for ${selectedProvider?.provider_name ?? "this service"} in ${regionName} right now.`}
              />
            ) : (
              <>
                <div
                  className={cn(
                    "grid grid-cols-2 gap-4 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6",
                    resultsQuery.isFetching && "opacity-60 transition-opacity",
                  )}
                >
                  {results.results.map((item) => (
                    <ContentCard key={`${item.content_type}-${item.id}`} content={item} />
                  ))}
                </div>

                {results.total_pages > 1 && (
                  <div className="mt-10">
                    <Pagination
                      page={results.page}
                      totalPages={Math.min(results.total_pages, 500)}
                      onPageChange={goToPage}
                      disabled={resultsQuery.isFetching}
                    />
                  </div>
                )}
              </>
            )}
          </>
        )}
      </section>
    </div>
  );
}
