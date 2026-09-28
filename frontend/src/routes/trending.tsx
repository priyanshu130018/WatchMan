import React from "react";
import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { z } from "zod";
import { Film, Flame, Tv } from "lucide-react";

import { ContentCard } from "@/components/ContentCard";
import { ContentGridSkeleton } from "@/components/Skeletons";
import { EmptyState, ErrorState } from "@/components/States";
import { catalogService } from "@/services/catalog";
import { TRENDING_ITEMS } from "@/lib/constants";
import { cn } from "@/lib/utils";

const trendingSearchSchema = z.object({
  type: z.enum(["all", "movie", "tv"]).optional(),
  window: z.enum(["day", "week"]).optional(),
});

export const Route = createFileRoute("/trending")({
  validateSearch: (search) => trendingSearchSchema.parse(search),
  component: TrendingRouteComponent,
});

function TrendingRouteComponent() {
  const search = Route.useSearch();
  const navigate = useNavigate();

  const activeType = search.type || "all";
  const activeWindow = search.window || "week";

  const queryKey = ["trending", activeType, activeWindow];

  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey,
    queryFn: async () => {
      if (activeType === "movie") {
        return catalogService.getTrendingMovies(activeWindow);
      }
      if (activeType === "tv") {
        return catalogService.getTrendingWebSeries(activeWindow);
      }
      return catalogService.getTrending({ type: "all", timeWindow: activeWindow });
    },
    staleTime: 60_000,
  });

  const handleTypeChange = (newType: "all" | "movie" | "tv") => {
    navigate({
      to: "/trending",
      search: { ...search, type: newType },
    });
  };

  const handleWindowChange = (newWindow: "day" | "week") => {
    navigate({
      to: "/trending",
      search: { ...search, window: newWindow },
    });
  };

  const items = data || [];

  const typeTabs: { key: "all" | "movie" | "tv"; label: string; icon?: React.ReactNode }[] = [
    { key: "all", label: "All Content" },
    { key: "movie", label: "Movies", icon: <Film size={13} aria-hidden="true" /> },
    { key: "tv", label: "Web Series", icon: <Tv size={13} aria-hidden="true" /> },
  ];

  return (
    <div className="mx-auto max-w-[1400px] px-4 py-8 sm:px-7">
      <header className="mb-8">
        <span className="inline-flex items-center gap-1.5 text-[11px] font-extrabold uppercase tracking-[0.16em] text-primary/80">
          <Flame size={14} className="text-primary" aria-hidden="true" /> Hot Right Now
        </span>
        <h1 className="mt-1 text-3xl font-bold tracking-tight text-foreground sm:text-4xl">
          Trending Worldwide
        </h1>
        <p className="mt-2 max-w-2xl text-sm text-muted-foreground">
          The most watched and talked-about movies and web series across the globe right now.
        </p>

        {/* Controls */}
        <div className="mt-6 flex flex-wrap items-center justify-between gap-4 rounded-2xl border border-border bg-card/50 p-3">
          {/* Content type tabs */}
          <div
            role="tablist"
            aria-label="Content type"
            className="flex flex-wrap items-center gap-2"
          >
            {typeTabs.map((tab) => {
              const active = activeType === tab.key;
              return (
                <button
                  key={tab.key}
                  type="button"
                  role="tab"
                  aria-selected={active}
                  onClick={() => handleTypeChange(tab.key)}
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

          {/* Time window switcher */}
          <div
            role="group"
            aria-label="Time window"
            className="flex items-center gap-1 rounded-full border border-border bg-secondary p-1"
          >
            {(
              [
                ["day", "Today"],
                ["week", "This Week"],
              ] as const
            ).map(([win, label]) => {
              const active = activeWindow === win;
              return (
                <button
                  key={win}
                  type="button"
                  aria-pressed={active}
                  onClick={() => handleWindowChange(win)}
                  className={cn(
                    "rounded-full px-3 py-1.5 text-xs font-semibold transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                    active
                      ? "bg-background text-foreground shadow-sm"
                      : "text-muted-foreground hover:text-foreground",
                  )}
                >
                  {label}
                </button>
              );
            })}
          </div>
        </div>
      </header>

      {/* Main grid state — trending is a single fixed page (never paginated). */}
      {isLoading ? (
        <ContentGridSkeleton count={TRENDING_ITEMS} />
      ) : isError ? (
        <ErrorState
          title="Could not load trending content"
          error={error}
          onRetry={() => refetch()}
        />
      ) : items.length === 0 ? (
        <EmptyState
          title="No trending titles found"
          description="Trending data is updating. Please check back in a few moments."
        />
      ) : (
        <ul className="grid grid-cols-2 gap-4 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6">
          {items.map((item) => (
            <li key={`${item.content_type}-${item.id || item.tmdb_id}`}>
              <ContentCard content={item} />
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
