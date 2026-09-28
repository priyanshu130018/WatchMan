import { useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ChevronLeft, ChevronRight, Film, Tv } from "lucide-react";

import { ContentCard } from "@/components/ContentCard";
import { ContentGridSkeleton } from "@/components/Skeletons";
import { Pagination } from "@/components/Pagination";
import { EmptyState, ErrorState } from "@/components/States";
import { imageUrl, type ContentType } from "@/types/content";
import { FALLBACK_OTT_REGIONS, ottService } from "@/services/ott";
import { CONTENT_PAGE_SIZE } from "@/lib/constants";
import { cn } from "@/lib/utils";

const DEFAULT_REGION = "IN";

export interface OttFilters {
  region?: string;
  type?: "movie" | "tv";
  provider?: number;
  page?: number;
}

export interface OttPageProps {
  searchParams: OttFilters;
  onUpdateFilters: (filters: OttFilters, options?: { replace?: boolean }) => void;
}

export function OttPage({ searchParams, onUpdateFilters }: OttPageProps) {
  // --- Applied state derived purely from the URL (the source of truth). ---
  const region = searchParams.region || DEFAULT_REGION;
  const contentType: ContentType = searchParams.type === "tv" ? "tv" : "movie";
  const page = Number(searchParams.page) > 1 ? Number(searchParams.page) : 1;
  const mediaNoun = contentType === "tv" ? "web series" : "movies";
  const mediaLabel = contentType === "tv" ? "Web Series" : "Movies";

  // Regions for the selector (falls back to a curated real-region list offline).
  const regionsQuery = useQuery({
    queryKey: ["ott", "regions"],
    queryFn: ottService.getRegions,
    staleTime: 24 * 60 * 60 * 1000,
  });
  const regions =
    regionsQuery.data && regionsQuery.data.length > 0 ? regionsQuery.data : FALLBACK_OTT_REGIONS;
  const regionName = regions.find((r) => r.iso_3166_1 === region)?.english_name || region;

  // Streaming providers for the region + media type. The backend returns them
  // already ordered by TMDB's region-specific display priority.
  const providersQuery = useQuery({
    queryKey: ["ott", "providers", region, contentType],
    queryFn: () => ottService.getProviders(region, contentType),
    staleTime: 60 * 60 * 1000,
  });
  const providers = providersQuery.data ?? [];

  // Default provider = the first entry in the backend's priority-ordered list for
  // this region + type. We never invent a popularity score or hardcode a service
  // (e.g. Netflix); we simply honor TMDB's own display ordering. The URL stays
  // authoritative — this only chooses which provider it should point at by default.
  const defaultProviderId = providers[0]?.provider_id;
  const urlProviderId = searchParams.provider ? Number(searchParams.provider) : undefined;
  const activeProviderId = urlProviderId ?? defaultProviderId;
  const selectedProvider = providers.find((p) => p.provider_id === activeProviderId);

  // Every commit rewrites the URL; only non-default values are emitted.
  const commit = (next: OttFilters, options?: { replace?: boolean }) => {
    const clean: OttFilters = {};
    if (next.region && next.region !== DEFAULT_REGION) clean.region = next.region;
    if (next.type === "tv") clean.type = "tv";
    if (next.provider) clean.provider = next.provider;
    if (next.page && next.page > 1) clean.page = next.page;
    onUpdateFilters(clean, options);
  };

  // Fill the default provider into the URL once providers load, so refresh,
  // Back/Forward, and shared links all resolve to a concrete provider. `replace`
  // avoids a history trap where landing on bare /ott and pressing Back re-fills.
  useEffect(() => {
    if (!searchParams.provider && defaultProviderId) {
      commit({ region, type: searchParams.type, provider: defaultProviderId }, { replace: true });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams.provider, defaultProviderId, region, searchParams.type]);

  // Titles available on the active provider. Driven by the effective provider so
  // results appear on first load, before the URL sync settles. Disabled until we
  // actually have a provider to query.
  const resultsQuery = useQuery({
    queryKey: ["ott", "discover", { region, contentType, providerId: activeProviderId, page }],
    queryFn: () =>
      ottService.discoverByProvider({
        contentType,
        providerId: activeProviderId as number,
        region,
        page,
      }),
    enabled: Boolean(activeProviderId),
    staleTime: 30_000,
  });

  // Changing region invalidates the current provider (a service in one region may
  // not exist in another) → reset provider + page; the effect re-selects a default.
  const changeRegion = (nextRegion: string) =>
    commit({ region: nextRegion, type: searchParams.type });
  // Keep the chosen provider across a movie/series switch (Netflix movies → Netflix
  // series), resetting to page 1 for the new media set.
  const changeType = (nextType: "movie" | "tv") =>
    commit({ region, type: nextType, provider: activeProviderId });
  const selectProvider = (id: number) => commit({ region, type: searchParams.type, provider: id });
  const goToPage = (nextPage: number) =>
    commit({ region, type: searchParams.type, provider: activeProviderId, page: nextPage });

  const results = resultsQuery.data;

  // --- Provider rail: horizontal scroll with conditional navigation arrows. ---
  const railRef = useRef<HTMLUListElement>(null);
  const [railScroll, setRailScroll] = useState({ left: false, right: false });

  const syncRailScroll = () => {
    const el = railRef.current;
    if (!el) return;
    const { scrollLeft, scrollWidth, clientWidth } = el;
    setRailScroll({
      left: scrollLeft > 4,
      right: scrollLeft + clientWidth < scrollWidth - 4,
    });
  };

  // Recompute arrow visibility on mount, when the provider set changes, and on resize.
  useEffect(() => {
    syncRailScroll();
    const el = railRef.current;
    if (!el) return;
    el.addEventListener("scroll", syncRailScroll, { passive: true });
    window.addEventListener("resize", syncRailScroll);
    return () => {
      el.removeEventListener("scroll", syncRailScroll);
      window.removeEventListener("resize", syncRailScroll);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [providers.length]);

  // Keep the active provider in view (deep-links / Back-Forward may target a
  // service far down the rail). Horizontal-only — never scrolls the page.
  useEffect(() => {
    const el = railRef.current;
    if (!el || !activeProviderId) return;
    const activeEl = el.querySelector<HTMLElement>(`[data-provider-id="${activeProviderId}"]`);
    if (activeEl) {
      const target = activeEl.offsetLeft - el.clientWidth / 2 + activeEl.clientWidth / 2;
      el.scrollTo({ left: Math.max(0, target), behavior: "smooth" });
    }
    syncRailScroll();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeProviderId, providers.length]);

  const scrollRail = (dir: -1 | 1) => {
    const el = railRef.current;
    if (!el) return;
    el.scrollBy({ left: dir * Math.max(el.clientWidth * 0.8, 240), behavior: "smooth" });
  };

  return (
    <div className="mx-auto max-w-[1400px] px-4 pb-24 pt-10 sm:px-7">
      {/* Header — compact hierarchy: eyebrow → question → live-data note. */}
      <header className="mb-9">
        <span className="text-[11px] font-extrabold uppercase tracking-[0.18em] text-primary">
          OTT
        </span>
        <h1 className="mt-1.5 text-2xl font-bold tracking-tight text-foreground sm:text-3xl">
          Where can you watch it?
        </h1>
        <p className="mt-2 max-w-xl text-sm text-muted-foreground">
          Pick a streaming service to browse the {mediaNoun} it&apos;s carrying in your region.
          Availability is reported live by JustWatch via TMDB.
        </p>
      </header>

      {/* Provider rail */}
      <section aria-labelledby="ott-rail-heading" className="mb-11">
        <div className="mb-4 flex items-end justify-between gap-4">
          <h2
            id="ott-rail-heading"
            className="text-xs font-semibold uppercase tracking-[0.14em] text-muted-foreground"
          >
            Streaming services
          </h2>
          <label className="flex items-center gap-2 text-xs text-muted-foreground">
            <span className="hidden sm:inline">Region</span>
            <select
              className="h-8 rounded-md border border-border bg-secondary px-2 text-xs font-medium text-foreground outline-none transition-colors focus-visible:ring-2 focus-visible:ring-ring"
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
        </div>
        {providersQuery.isLoading ? (
          <ul
            className="flex gap-3 overflow-hidden px-1 pb-6 pt-2"
            aria-busy="true"
            aria-label="Loading streaming services"
          >
            {Array.from({ length: 10 }).map((_, i) => (
              <li
                key={i}
                className="h-[108px] w-[92px] shrink-0 animate-pulse rounded-xl border border-border bg-secondary"
                aria-hidden="true"
              />
            ))}
          </ul>
        ) : providersQuery.isError ? (
          <ErrorState
            title="Could not load streaming services"
            error={providersQuery.error}
            onRetry={() => void providersQuery.refetch()}
          />
        ) : providers.length === 0 ? (
          <EmptyState
            title="No streaming services found"
            description={`TMDB has no ${mediaNoun} provider data for ${regionName}. Try another region.`}
          />
        ) : (
          <div className="relative">
            {/* Edge fades + arrows appear only when there is more to scroll. */}
            {railScroll.left && (
              <div className="pointer-events-none absolute inset-y-0 left-0 z-10 w-12 bg-gradient-to-r from-background to-transparent" />
            )}
            {railScroll.right && (
              <div className="pointer-events-none absolute inset-y-0 right-0 z-10 w-12 bg-gradient-to-l from-background to-transparent" />
            )}
            {railScroll.left && (
              <button
                type="button"
                onClick={() => scrollRail(-1)}
                aria-label="Scroll streaming services left"
                className="absolute left-0 top-1/2 z-20 hidden h-9 w-9 -translate-y-1/2 items-center justify-center rounded-full border border-border bg-card/90 text-foreground shadow-md backdrop-blur transition-colors hover:border-primary/60 hover:text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring sm:inline-flex"
              >
                <ChevronLeft size={18} aria-hidden="true" />
              </button>
            )}
            {railScroll.right && (
              <button
                type="button"
                onClick={() => scrollRail(1)}
                aria-label="Scroll streaming services right"
                className="absolute right-0 top-1/2 z-20 hidden h-9 w-9 -translate-y-1/2 items-center justify-center rounded-full border border-border bg-card/90 text-foreground shadow-md backdrop-blur transition-colors hover:border-primary/60 hover:text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring sm:inline-flex"
              >
                <ChevronRight size={18} aria-hidden="true" />
              </button>
            )}

            <ul
              ref={railRef}
              className="no-scrollbar flex items-stretch gap-3 overflow-x-auto scroll-smooth px-1 pb-6 pt-2"
            >
              {providers.map((p) => {
                const active = p.provider_id === activeProviderId;
                const logo = imageUrl(p.logo_path, "w185");
                return (
                  <li key={p.provider_id} className="shrink-0">
                    <button
                      type="button"
                      data-provider-id={p.provider_id}
                      onClick={() => selectProvider(p.provider_id)}
                      aria-pressed={active}
                      aria-current={active ? "true" : undefined}
                      aria-label={
                        active ? `${p.provider_name}, selected` : `Select ${p.provider_name}`
                      }
                      title={p.provider_name}
                      className={cn(
                        "group flex min-h-[108px] w-[92px] flex-col items-center justify-center gap-2 rounded-xl border p-3 text-center outline-none transition-all duration-200 ease-out focus-visible:ring-2 focus-visible:ring-ring",
                        active
                          ? "scale-[1.04] border-primary bg-primary/10 shadow-[0_6px_20px_-8px] shadow-primary/40 ring-1 ring-primary"
                          : "border-border bg-card hover:-translate-y-0.5 hover:border-primary/50 hover:bg-accent",
                      )}
                    >
                      {logo ? (
                        <img
                          src={logo}
                          alt=""
                          loading="lazy"
                          className={cn(
                            "rounded-lg object-cover transition-all duration-200 ease-out",
                            active ? "h-14 w-14" : "h-11 w-11 group-hover:scale-[1.02]",
                          )}
                        />
                      ) : (
                        <span
                          className={cn(
                            "grid place-items-center rounded-lg bg-secondary text-muted-foreground",
                            active ? "h-14 w-14" : "h-11 w-11",
                          )}
                          aria-hidden="true"
                        >
                          <Tv size={active ? 26 : 20} />
                        </span>
                      )}
                      <span
                        className={cn(
                          "line-clamp-2 text-[11px] leading-tight transition-colors",
                          active ? "font-semibold text-primary" : "font-medium text-foreground/90",
                        )}
                      >
                        {p.provider_name}
                      </span>
                    </button>
                  </li>
                );
              })}
            </ul>
          </div>
        )}
      </section>
      {/* Selected provider + results */}
      <section aria-labelledby="ott-results-heading">
        {activeProviderId ? (
          <>
            {/* Selected provider header */}
            <div className="mb-5 flex items-center gap-3">
              {selectedProvider && imageUrl(selectedProvider.logo_path, "w185") && (
                <img
                  src={imageUrl(selectedProvider.logo_path, "w185")}
                  alt=""
                  className="h-9 w-9 shrink-0 rounded-lg object-cover"
                />
              )}
              <div className="min-w-0">
                <h2
                  id="ott-results-heading"
                  className="truncate text-xl font-bold tracking-tight text-foreground sm:text-2xl"
                >
                  {selectedProvider ? selectedProvider.provider_name : "Available titles"}
                </h2>
                <p className="text-sm text-muted-foreground">
                  Movies and series available on {selectedProvider?.provider_name ?? "this service"}{" "}
                  in {regionName}
                </p>
              </div>
            </div>
            {/* Movies / Web Series segmented control */}
            <div
              role="group"
              aria-label="Content type"
              className="mb-7 inline-flex rounded-lg border border-border bg-secondary p-1"
            >
              {(
                [
                  ["movie", "Movies", <Film key="m" size={15} aria-hidden="true" />],
                  ["tv", "Web Series", <Tv key="t" size={15} aria-hidden="true" />],
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
                      "inline-flex items-center gap-1.5 rounded-md px-4 py-1.5 text-sm font-semibold outline-none transition-colors focus-visible:ring-2 focus-visible:ring-ring",
                      active
                        ? "bg-primary text-watchman-black shadow-sm"
                        : "text-muted-foreground hover:text-foreground",
                    )}
                  >
                    {icon}
                    {label}
                  </button>
                );
              })}
            </div>
            {/* Content grid */}
            <h3 className="mb-4 text-base font-semibold text-foreground">
              {mediaLabel}
              <span className="ml-2 text-sm font-normal text-muted-foreground">
                in {regionName}
              </span>
            </h3>

            {resultsQuery.isLoading ? (
              <ContentGridSkeleton count={CONTENT_PAGE_SIZE} />
            ) : resultsQuery.isError ? (
              <ErrorState
                title="Could not load titles"
                error={resultsQuery.error}
                onRetry={() => void resultsQuery.refetch()}
              />
            ) : !results || results.results.length === 0 ? (
              <EmptyState
                title={`No ${mediaNoun} available`}
                description={`No ${mediaNoun} available for ${
                  selectedProvider?.provider_name ?? "this provider"
                } in your region.`}
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
        ) : providersQuery.isLoading ? (
          <ContentGridSkeleton count={CONTENT_PAGE_SIZE} />
        ) : null}
      </section>
    </div>
  );
}
