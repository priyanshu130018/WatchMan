import React from "react";
import { useQueries, useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { Play, Search, Sparkles } from "lucide-react";

import { ContentSection } from "@/components/ContentSection";
import { ErrorState } from "@/components/States";
import { Button } from "@/components/ui/button";
import { catalogService } from "@/services/catalog";
import { recommendationService } from "@/services/recommendations";
import { useAuthStore } from "@/store/authStore";
import type { ContentItem } from "@/types/content";

const LIVE_REFRESH_MS = 60_000;

export function Home() {
  const user = useAuthStore((s) => s.user);

  // Landing page rails. The public catalogue (Trending → Top Rated → Movies →
  // Web Series) is identical for everyone. A personalized "{Name}, You May Like"
  // rail is layered in directly below the Hero for signed-in users who have
  // enough real activity — see the recommendation query and `isPersonalized`
  // gate below. It reuses the existing recommendation engine as the source of
  // truth; we never score in React or fabricate personalization here.
  const [trendingQuery, topRatedMoviesQuery, topRatedTvQuery, moviesQuery, webSeriesQuery] =
    useQueries({
      queries: [
        {
          queryKey: ["homepage", "trending", "all"],
          queryFn: () => catalogService.getTrending({ type: "all", timeWindow: "week" }),
          refetchInterval: LIVE_REFRESH_MS,
        },
        {
          queryKey: ["homepage", "movies", "top-rated"],
          queryFn: () => catalogService.getTopRatedMovies(1),
          refetchInterval: LIVE_REFRESH_MS,
        },
        {
          queryKey: ["homepage", "tv", "top-rated"],
          queryFn: () => catalogService.getTopRatedWebSeries(1),
          refetchInterval: LIVE_REFRESH_MS,
        },
        {
          queryKey: ["homepage", "movies", "all"],
          queryFn: () => catalogService.getMovies({ page: 1, limit: 18, sort: "popularity_desc" }),
          refetchInterval: LIVE_REFRESH_MS,
        },
        {
          queryKey: ["homepage", "tv", "all"],
          queryFn: () =>
            catalogService.getWebSeries({ page: 1, limit: 18, sort: "popularity_desc" }),
          refetchInterval: LIVE_REFRESH_MS,
        },
      ],
    });

  const trending = trendingQuery.data || [];
  const topRatedMovies = topRatedMoviesQuery.data || [];
  const topRatedTv = topRatedTvQuery.data || [];
  const movies = moviesQuery.data?.results || [];
  const webSeries = webSeriesQuery.data?.results || [];

  // Personalized rail — sourced ONLY from the existing recommendation engine
  // (/api/recommendations → UnifiedRecommendationService → HybridRanker). No
  // client-side scoring, no second algorithm. Only runs for signed-in users.
  const recommendationsQuery = useQuery({
    queryKey: ["homepage", "recommendations", user?.id],
    queryFn: () => recommendationService.getRecommendations({ contentType: "all", limit: 18 }),
    enabled: Boolean(user),
  });
  const recItems = recommendationsQuery.data?.items ?? [];

  // Cold-start detection reuses the backend's own `sources` stamp: its fallback
  // path marks every item "cold_start_popularity" when the engine lacks enough
  // real signal for this user. On the homepage we NEVER present popularity as
  // personalization — if the engine is cold (or the user is a guest), the whole
  // section is hidden rather than shown with a misleading label or fake rail.
  const isColdStart = recItems.some((it) =>
    (it.sources ?? []).some((s) => s.includes("cold_start")),
  );
  const isPersonalized = Boolean(user) && recItems.length > 0 && !isColdStart;
  const displayName =
    user?.full_name?.trim() ||
    user?.username?.trim() ||
    (user?.email ? user.email.split("@")[0] : "");
  const personalizedTitle = displayName ? `${displayName}, You May Like` : "You May Like";

  // "Top Rated Worldwide" merges the highest-rated movies and web series into a
  // single cross-type rail, ordered by audience score. Dedupe defensively by
  // content_type + id so a title never appears twice.
  const topRatedWorldwide = React.useMemo<ContentItem[]>(() => {
    const seen = new Set<string>();
    return [...topRatedMovies, ...topRatedTv]
      .filter((item) => {
        const key = `${item.content_type}-${item.tmdb_id || item.id}`;
        if (seen.has(key)) return false;
        seen.add(key);
        return true;
      })
      .sort((a, b) => (b.vote_average || 0) - (a.vote_average || 0));
  }, [topRatedMovies, topRatedTv]);

  // Hero sources from global trending, falling back through top-rated / movies
  // so the banner is never empty during a partial outage.
  const heroItem: ContentItem | undefined = trending[0] || topRatedWorldwide[0] || movies[0];
  const heroPath = heroItem?.content_type === "tv" ? "/web-series/$id" : "/movie/$id";

  // Individual rails silently collapse when a single query fails (a partial
  // outage shouldn't blank the page). But if EVERY row failed the API is
  // effectively down — surface one actionable error with a retry.
  const catalogQueries = [
    trendingQuery,
    topRatedMoviesQuery,
    topRatedTvQuery,
    moviesQuery,
    webSeriesQuery,
  ];
  const allCatalogFailed = catalogQueries.every((q) => q.isError);
  return (
    <div>
      {/* Hero Showcase Banner */}
      <section className="relative flex min-h-[560px] items-center overflow-hidden md:h-[76vh] md:max-h-[700px]">
        {heroItem?.backdrop_url ? (
          <img
            src={heroItem.backdrop_url}
            alt=""
            className="absolute inset-0 h-full w-full object-cover object-center"
          />
        ) : null}
        <div className="absolute inset-0 bg-gradient-to-r from-background via-background/90 to-background/40" />
        <div className="absolute inset-0 bg-gradient-to-t from-background to-transparent to-[38%]" />

        <div className="relative z-10 mx-auto w-full max-w-[1400px] px-4 py-16 sm:px-7">
          <p className="inline-flex items-center gap-2 text-[11px] font-extrabold uppercase tracking-[0.16em] text-primary">
            <Sparkles size={14} aria-hidden="true" /> AI-powered entertainment discovery
          </p>
          <h1 className="mt-4 max-w-3xl text-4xl font-extrabold leading-[0.95] tracking-tight sm:text-6xl lg:text-7xl">
            {heroItem ? (
              <>
                {heroItem.title}
                {heroItem.tagline && (
                  <span className="mt-3 block text-lg font-normal tracking-normal text-muted-foreground sm:text-xl">
                    {heroItem.tagline}
                  </span>
                )}
              </>
            ) : (
              <>
                Find your next <span className="text-brand-gradient">great watch.</span>
              </>
            )}
          </h1>
          <p className="mt-5 line-clamp-3 max-w-xl text-base leading-relaxed text-muted-foreground sm:text-lg">
            {heroItem?.overview ||
              "Discover movies and web series curated to your personal taste using machine-learned embeddings, verified peer ratings, and trending catalog insights."}
          </p>
          <div className="mt-7 flex flex-wrap gap-3">
            {heroItem ? (
              <Button asChild variant="brand" size="lg">
                <Link to={heroPath} params={{ id: String(heroItem.tmdb_id || heroItem.id) }}>
                  <Play size={17} fill="currentColor" aria-hidden="true" /> Explore Now
                </Link>
              </Button>
            ) : (
              <Button asChild variant="brand" size="lg">
                <Link to="/movie">
                  <Play size={17} fill="currentColor" aria-hidden="true" /> Browse Catalog
                </Link>
              </Button>
            )}
            <Button asChild variant="outline" size="lg">
              <Link to="/search">
                <Search size={17} aria-hidden="true" /> Search Everything
              </Link>
            </Button>
          </div>
        </div>
      </section>
      {/* Primary Homepage Content Sections */}
      <div className="mx-auto max-w-[1400px] px-4 sm:px-7">
        {allCatalogFailed && (
          <div className="pt-11">
            <ErrorState
              title="We couldn't load the catalog"
              error={trendingQuery.error}
              onRetry={() => catalogQueries.forEach((q) => q.refetch())}
            />
          </div>
        )}

        {/* 2. Personalized — "{Name}, You May Like". Rendered ONLY when the
            existing engine returns genuine personalized signal (signed-in,
            non-cold-start). Hidden for guests and cold-start users so we never
            label popularity as personalization. */}
        {isPersonalized && (
          <ContentSection
            title={personalizedTitle}
            subtitle="Picked for you by WatchMan's hybrid engine"
            items={recItems}
            isLoading={recommendationsQuery.isLoading}
            showTypeBadge
            maxItems={18}
            exploreLink="/recommendation"
          />
        )}

        {/* 3. Trending Now — global combined trending for the week */}
        <ContentSection
          title="Trending Now"
          subtitle="What the world is watching this week"
          items={trending}
          isLoading={trendingQuery.isLoading}
          showTypeBadge
          maxItems={18}
          exploreLink="/trending"
        />

        {/* 4. Top Rated Worldwide — highest-rated movies + web series merged */}
        <ContentSection
          title="Top Rated Worldwide"
          subtitle="Highest audience scores across movies & series"
          items={topRatedWorldwide}
          isLoading={topRatedMoviesQuery.isLoading || topRatedTvQuery.isLoading}
          showTypeBadge
          maxItems={18}
          exploreLink="/movie"
          exploreSearch={{ sort: "vote_average_desc" }}
        />

        {/* 5. Movies */}
        <ContentSection
          title="Movies"
          subtitle="Explore the movie catalog"
          items={movies}
          isLoading={moviesQuery.isLoading}
          maxItems={18}
          exploreLink="/movie"
        />

        {/* 6. Web Series */}
        <ContentSection
          title="Web Series"
          subtitle="Explore the series catalog"
          items={webSeries}
          isLoading={webSeriesQuery.isLoading}
          maxItems={18}
          exploreLink="/web-series"
        />
      </div>
    </div>
  );
}
