import React from "react";
import { useQueries, useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { Play, Search, Sparkles } from "lucide-react";

import { ContentSection } from "@/components/ContentSection";
import { PersonalizedShelf } from "@/components/PersonalizedShelf";
import { ErrorState } from "@/components/States";
import { Button } from "@/components/ui/button";
import { catalogService } from "@/services/catalog";
import { recommendationService } from "@/services/recommendations";
import { CONTENT_PAGE_SIZE } from "@/lib/constants";
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
          queryFn: () =>
            catalogService.getMovies({
              page: 1,
              limit: CONTENT_PAGE_SIZE,
              sort: "popularity_desc",
            }),
          refetchInterval: LIVE_REFRESH_MS,
        },
        {
          queryKey: ["homepage", "tv", "all"],
          queryFn: () =>
            catalogService.getWebSeries({
              page: 1,
              limit: CONTENT_PAGE_SIZE,
              sort: "popularity_desc",
            }),
          refetchInterval: LIVE_REFRESH_MS,
        },
      ],
    });

  const trending = trendingQuery.data || [];
  const topRatedMovies = topRatedMoviesQuery.data || [];
  const topRatedTv = topRatedTvQuery.data || [];
  const movies = moviesQuery.data?.results || [];
  const webSeries = webSeriesQuery.data?.results || [];

  // Personalized shelves:
  // Each shelf has its own backend source/query and its own React Query cache key.
  // 1. You Must Like (highest-confidence recommendations from the hybrid engine)
  const mustLikeQuery = useQuery({
    queryKey: ["homepage", "personalized", "must_like", user?.id],
    queryFn: () => recommendationService.getMustLike({ limit: 12 }),
    enabled: Boolean(user),
    staleTime: 5 * 60_000,
  });

  // 2. You Already Watched & Liked (meaningful watch + positive feedback signals)
  const watchedLikedQuery = useQuery({
    queryKey: ["homepage", "personalized", "watched_liked", user?.id],
    queryFn: () => recommendationService.getWatchedLiked({ limit: 12 }),
    enabled: Boolean(user),
    staleTime: 5 * 60_000,
  });

  // 3. Continue Watching (real in-progress playback; frequent polling/refresh)
  const continueWatchingQuery = useQuery({
    queryKey: ["homepage", "personalized", "continue_watching", user?.id],
    queryFn: () => recommendationService.getContinueWatching({ limit: 12 }),
    enabled: Boolean(user),
    refetchInterval: 30_000,
  });

  const mustLikeItems = mustLikeQuery.data?.items ?? [];
  const watchedLikedItems = watchedLikedQuery.data?.items ?? [];
  const continueWatchingItems = continueWatchingQuery.data?.items ?? [];

  // Defensive cross-shelf deduplication in priority order:
  // 1. Continue Watching
  // 2. You Already Watched & Liked
  // 3. You Must Like
  const cwIds = React.useMemo(
    () => new Set(continueWatchingItems.map((it) => it.id || it.tmdb_id)),
    [continueWatchingItems],
  );
  const dedupedWatchedLiked = React.useMemo(
    () => watchedLikedItems.filter((it) => !cwIds.has(it.id || it.tmdb_id)),
    [watchedLikedItems, cwIds],
  );
  const wlIds = React.useMemo(
    () => new Set(dedupedWatchedLiked.map((it) => it.id || it.tmdb_id)),
    [dedupedWatchedLiked],
  );
  const dedupedMustLike = React.useMemo(
    () =>
      mustLikeItems.filter(
        (it) => !cwIds.has(it.id || it.tmdb_id) && !wlIds.has(it.id || it.tmdb_id),
      ),
    [mustLikeItems, cwIds, wlIds],
  );

  const hasPersonalizedContent =
    continueWatchingItems.length > 0 ||
    dedupedWatchedLiked.length > 0 ||
    dedupedMustLike.length > 0;

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

        {/* 2. Personalized Area — PERSONALIZED FOR YOU
            Rendered ONLY when the user is signed in and has genuine personalized activity.
            Independent horizontal shelves:
            1. You Must Like
            2. You Already Watched & Liked
            3. Continue Watching */}
        {Boolean(user) && hasPersonalizedContent && (
          <div className="pt-6">
            <div className="flex items-center gap-2 mb-1">
              <Sparkles size={16} className="text-primary" aria-hidden="true" />
              <span className="text-xs font-black uppercase tracking-[0.2em] text-primary">
                Personalized For You
              </span>
            </div>

            {/* Shelf 1: You Must Like */}
            {dedupedMustLike.length > 0 && (
              <PersonalizedShelf
                title="You Must Like"
                subtitle="Picked from your taste and activity"
                items={dedupedMustLike}
                sectionKey="must_like"
                isLoading={mustLikeQuery.isLoading}
                exploreLink="/recommendation"
              />
            )}

            {/* Shelf 2: You Already Watched & Liked */}
            {dedupedWatchedLiked.length > 0 && (
              <PersonalizedShelf
                title="You Already Watched & Liked"
                subtitle="Titles you completed and enjoyed"
                items={dedupedWatchedLiked}
                sectionKey="watched_liked"
                isLoading={watchedLikedQuery.isLoading}
                exploreLink="/history"
              />
            )}

            {/* Shelf 3: Continue Watching */}
            {continueWatchingItems.length > 0 && (
              <PersonalizedShelf
                title="Continue Watching"
                subtitle="Pick up where you left off"
                items={continueWatchingItems}
                sectionKey="continue_watching"
                isLoading={continueWatchingQuery.isLoading}
                exploreLink="/history"
              />
            )}
          </div>
        )}

        {/* 3. Trending Now — global combined trending for the week */}
        <ContentSection
          title="Trending Now"
          subtitle="What the world is watching this week"
          items={trending}
          isLoading={trendingQuery.isLoading}
          showTypeBadge
          maxItems={CONTENT_PAGE_SIZE}
          exploreLink="/trending"
        />

        {/* 4. Top Rated Worldwide — highest-rated movies + web series merged */}
        <ContentSection
          title="Top Rated Worldwide"
          subtitle="Highest audience scores across movies & series"
          items={topRatedWorldwide}
          isLoading={topRatedMoviesQuery.isLoading || topRatedTvQuery.isLoading}
          showTypeBadge
          maxItems={CONTENT_PAGE_SIZE}
          exploreLink="/movie"
          exploreSearch={{ sort: "vote_average_desc" }}
        />

        {/* 5. Movies */}
        <ContentSection
          title="Movies"
          subtitle="Explore the movie catalog"
          items={movies}
          isLoading={moviesQuery.isLoading}
          maxItems={CONTENT_PAGE_SIZE}
          exploreLink="/movie"
        />

        {/* 6. Web Series */}
        <ContentSection
          title="Web Series"
          subtitle="Explore the series catalog"
          items={webSeries}
          isLoading={webSeriesQuery.isLoading}
          maxItems={CONTENT_PAGE_SIZE}
          exploreLink="/web-series"
        />
      </div>
    </div>
  );
}
