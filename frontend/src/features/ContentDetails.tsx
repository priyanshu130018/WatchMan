import React, { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate } from "@tanstack/react-router";
import {
  ArrowLeft,
  Bookmark,
  Calendar,
  Clock,
  ExternalLink,
  Film,
  Image as ImageIcon,
  Layers,
  MessageSquare,
  MonitorPlay,
  Play,
  Star,
  Tv,
} from "lucide-react";

import { ContentCard } from "@/components/ContentCard";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { DetailSkeleton } from "@/components/Skeletons";
import { ErrorState } from "@/components/States";
import { RatingModal } from "@/components/RatingModal";
import { VideoModal } from "@/components/VideoModal";
import { ReviewsSection } from "@/components/ReviewsSection";
import { WatchmanScoreCard } from "@/components/WatchmanScoreCard";
import { catalogService } from "@/services/catalog";
import { recommendationService } from "@/services/recommendations";
import { userService } from "@/services/user";
import { FALLBACK_OTT_REGIONS, type OttProvider, ottService } from "@/services/ott";
import { useAuthStore } from "@/store/authStore";
import { getApiErrorMessage } from "@/lib/api";
import { toast } from "sonner";
import { type ContentType, imageUrl, type VideoItem } from "@/types/content";
import {
  rating as formatRating,
  runtime as formatRuntime,
  year as formatYear,
} from "@/utils/format";

const WATCH_PROVIDER_GROUPS = [
  { key: "flatrate", label: "Stream" },
  { key: "free", label: "Free" },
  { key: "ads", label: "Free with Ads" },
  { key: "rent", label: "Rent" },
  { key: "buy", label: "Buy" },
] as const;

export interface ContentDetailsProps {
  contentType: ContentType;
  id: number;
}

export function ContentDetails({ contentType, id }: ContentDetailsProps) {
  const token = useAuthStore((state) => state.token);
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const [isRatingModalOpen, setIsRatingModalOpen] = useState(false);
  const [selectedVideo, setSelectedVideo] = useState<VideoItem | null>(null);
  const [watchRegion, setWatchRegion] = useState("IN");

  const isTv = contentType === "tv";
  // Content-type-aware noun for copy (e.g. the error title). Derived from the
  // actual content type; falls back to the generic "content" for any
  // unexpected/ambiguous type instead of mislabeling a movie as a web series.
  const contentNoun =
    contentType === "movie" ? "movie" : contentType === "tv" ? "web series" : "content";

  // 1. Fetch Content Details
  const detailQueryKey = [isTv ? "web-series" : "movies", "detail", id];
  const detailQuery = useQuery({
    queryKey: detailQueryKey,
    queryFn: () =>
      isTv ? catalogService.getWebSeriesDetail(id) : catalogService.getMovieDetail(id),
    staleTime: 60_000,
  });

  // 2. Fetch Similar Content via Recommendations API
  const similarQueryKey = ["recommendations", "similar", contentType, id];
  const similarQuery = useQuery({
    queryKey: similarQueryKey,
    queryFn: async () => {
      try {
        const results = await recommendationService.getSimilarContent(contentType, id, 10);
        if (results && results.length > 0) return results;
      } catch (e) {
        // Fallback to catalog similar
      }
      return isTv ? catalogService.getWebSeriesSimilar(id) : catalogService.getMovieSimilar(id);
    },
    enabled: detailQuery.isSuccess,
    staleTime: 60_000,
  });

  // 3. User Saved & Rating States
  const favoritesQuery = useQuery({
    queryKey: ["favorites"],
    queryFn: userService.favorites,
    enabled: Boolean(token),
  });

  const ratingsQuery = useQuery({
    queryKey: ["ratings"],
    queryFn: userService.ratings,
    enabled: Boolean(token),
  });

  // 4. Detail-only enrichment (fetched once details load, never on cards):
  //    where-to-watch offers, an image gallery, and TMDB community reviews.
  const regionsQuery = useQuery({
    queryKey: ["ott", "regions"],
    queryFn: ottService.getRegions,
    staleTime: 24 * 60 * 60 * 1000,
    enabled: detailQuery.isSuccess,
  });
  const watchRegions =
    regionsQuery.data && regionsQuery.data.length > 0 ? regionsQuery.data : FALLBACK_OTT_REGIONS;

  const watchProvidersQuery = useQuery({
    queryKey: ["watch-providers", contentType, id, watchRegion],
    queryFn: () => ottService.getWatchProviders(contentType, id, watchRegion),
    enabled: detailQuery.isSuccess,
    staleTime: 6 * 60 * 60 * 1000,
  });

  const imagesQuery = useQuery({
    queryKey: ["images", contentType, id],
    queryFn: () => catalogService.getImages(contentType, id),
    enabled: detailQuery.isSuccess,
    staleTime: 24 * 60 * 60 * 1000,
  });

  const tmdbReviewsQuery = useQuery({
    queryKey: ["tmdb-reviews", contentType, id],
    queryFn: () => catalogService.getTmdbReviews(contentType, id, 1),
    enabled: detailQuery.isSuccess,
    staleTime: 60 * 60 * 1000,
  });

  const content = detailQuery.data;

  const isSaved =
    favoritesQuery.data?.some(
      (item) =>
        item.content_id === id ||
        item.movie_id === id ||
        (item.content && item.content.tmdb_id === id),
    ) ?? false;

  const userRating = ratingsQuery.data?.find(
    (item) => item.content_id === id || item.movie_id === id,
  )?.rating;

  // Mutations
  const saveMutation = useMutation({
    mutationFn: async () => {
      if (!token) {
        navigate({ to: "/login" });
        return;
      }
      if (isSaved) {
        return userService.removeFavorite(contentType, id);
      } else {
        return userService.addFavorite({
          content_type: contentType,
          tmdb_id: id,
          movie_id: id,
        });
      }
    },
    onSuccess: async () => {
      if (!token) return;
      await queryClient.invalidateQueries({ queryKey: ["favorites"] });
      await queryClient.invalidateQueries({ queryKey: ["recommendations"] });
      toast.success(isSaved ? "Removed from your library." : "Saved to your watchlist.");
    },
    onError: (err) => toast.error(getApiErrorMessage(err)),
  });

  const handleRate = async (score: number) => {
    if (!token) {
      navigate({ to: "/login" });
      return;
    }
    try {
      await userService.rateContent(contentType, id, score);
      await queryClient.invalidateQueries({ queryKey: ["ratings"] });
      await queryClient.invalidateQueries({ queryKey: ["recommendations"] });
      toast.success(`Rating saved: ${score}/10.`);
    } catch (err) {
      toast.error(getApiErrorMessage(err));
    }
  };

  // Log a watch-history entry when the user plays the trailer. WatchMan has no
  // streaming/playback of full titles, so trailer playback is the only genuine
  // "watch" interaction the product supports — we do NOT fabricate a streaming
  // system. Best-effort and silent on failure so playback is never blocked.
  const logTrailerView = (video: VideoItem) => {
    setSelectedVideo(video);
    if (!token) return;
    userService
      .addHistory({ content_type: contentType, tmdb_id: id, progress: 0 })
      .then(() => {
        queryClient.invalidateQueries({ queryKey: ["watchHistory"] });
      })
      .catch(() => {
        // Non-blocking: watch-history logging must never interrupt playback.
      });
  };

  if (detailQuery.isLoading) {
    return <DetailSkeleton />;
  }

  if (detailQuery.isError || !content) {
    return (
      <div className="mx-auto max-w-[1400px] px-4 pt-16 sm:px-7">
        <ErrorState
          title={`Could not load ${contentNoun} details`}
          error={detailQuery.error}
          onRetry={() => detailQuery.refetch()}
        />
      </div>
    );
  }

  const primaryTrailer =
    content.videos?.find(
      (v) => (v.type === "Trailer" || v.type === "Teaser") && v.site.toLowerCase() === "youtube",
    ) || content.videos?.[0];

  const releaseYear = formatYear(content.release_date || content.first_air_date);
  const ratingScore = content.vote_average ? formatRating(content.vote_average) : null;
  const directors =
    content.crew?.filter((c) => c.job === "Director" || c.job === "Executive Producer") || [];
  const topCast = content.cast?.slice(0, 12) || [];
  const similarItems = similarQuery.data || [];

  // Enrichment derived state.
  const offers = watchProvidersQuery.data;
  const hasOffers = offers
    ? WATCH_PROVIDER_GROUPS.some((g) => (offers[g.key] || []).length > 0)
    : false;
  const backdrops = imagesQuery.data?.backdrops ?? [];
  const posters = imagesQuery.data?.posters ?? [];
  const galleryImages = [...backdrops, ...posters].slice(0, 16);
  const tmdbReviews = tmdbReviewsQuery.data?.results ?? [];
  const watchRegionName =
    watchRegions.find((r) => r.iso_3166_1 === watchRegion)?.english_name || watchRegion;

  return (
    <div>
      {/* Detail Hero Banner */}
      <section className="relative min-h-[600px] overflow-hidden">
        {content.backdrop_url && (
          <img
            src={content.backdrop_url}
            alt=""
            className="absolute inset-0 h-full w-full object-cover object-center"
            aria-hidden="true"
          />
        )}
        <div className="absolute inset-0 bg-gradient-to-r from-background via-background/90 to-background/40" />
        <div className="absolute inset-0 bg-gradient-to-t from-background to-transparent to-[42%]" />

        <div className="relative z-10 mx-auto max-w-[1400px] px-4 pb-16 pt-8 sm:px-7">
          <Link
            to={isTv ? "/web-series" : "/movie"}
            className="mb-6 inline-flex items-center gap-2 rounded text-sm text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            <ArrowLeft size={16} aria-hidden="true" /> Back to {isTv ? "Web Series" : "Movies"}
          </Link>

          <div className="flex flex-col md:flex-row items-center md:items-start gap-8 lg:gap-12">
            {/* Poster */}
            <div className="w-56 sm:w-64 md:w-72 lg:w-80 shrink-0">
              {content.poster_url ? (
                <img
                  src={content.poster_url}
                  alt={`Poster for ${content.title}`}
                  className="w-full rounded-2xl border border-border/80 shadow-2xl object-cover aspect-[2/3]"
                />
              ) : (
                <div className="flex aspect-[2/3] w-full flex-col items-center justify-center rounded-2xl border border-border bg-card p-4 text-center text-muted-foreground">
                  {isTv ? (
                    <Tv size={48} aria-hidden="true" />
                  ) : (
                    <Film size={48} aria-hidden="true" />
                  )}
                  <span className="mt-2 text-xs">{content.title}</span>
                </div>
              )}
            </div>

            {/* Main Info */}
            <div className="flex-1 min-w-0 space-y-4">
              <div className="flex flex-wrap items-center gap-2">
                <Badge variant="brand">{isTv ? "WEB SERIES" : "MOVIE"}</Badge>
                {content.genres?.map((g) => (
                  <Badge key={g.id || g.name} variant="outline">
                    {g.name}
                  </Badge>
                ))}
              </div>

              <h1 className="text-3xl font-extrabold leading-tight tracking-tight text-foreground sm:text-5xl">
                {content.title}
              </h1>

              {content.tagline && <p className="text-lg italic text-primary">{content.tagline}</p>}

              {/* Facts & Metadata */}
              <div className="flex flex-wrap items-center gap-4 text-sm text-muted-foreground sm:gap-6">
                {ratingScore && (
                  <span className="flex items-center gap-1.5 font-bold text-yellow-400 bg-yellow-400/10 px-3 py-1 rounded-full">
                    <Star size={15} fill="currentColor" /> {ratingScore} / 10
                    {content.vote_count ? (
                      <span className="text-xs text-muted-foreground font-normal">
                        ({content.vote_count.toLocaleString()} votes)
                      </span>
                    ) : null}
                  </span>
                )}

                {releaseYear && (
                  <span className="flex items-center gap-1.5">
                    <Calendar size={15} className="text-muted-foreground" />{" "}
                    {content.release_date || content.first_air_date}
                  </span>
                )}

                {!isTv && content.runtime ? (
                  <span className="flex items-center gap-1.5">
                    <Clock size={15} className="text-muted-foreground" />{" "}
                    {formatRuntime(content.runtime)}
                  </span>
                ) : null}

                {isTv && (content.number_of_seasons || content.number_of_episodes) ? (
                  <span className="flex items-center gap-1.5">
                    <Layers size={15} className="text-muted-foreground" />
                    {content.number_of_seasons ? `${content.number_of_seasons} Seasons` : ""}
                    {content.number_of_seasons && content.number_of_episodes ? " • " : ""}
                    {content.number_of_episodes ? `${content.number_of_episodes} Episodes` : ""}
                  </span>
                ) : null}
              </div>

              {/* External ratings (IMDb / Rotten Tomatoes / Metacritic via OMDb) */}
              {(content.imdb_rating || (content.ratings && content.ratings.length > 0)) && (
                <div className="flex flex-wrap items-center gap-2 pt-1">
                  {content.imdb_rating && (
                    <span className="inline-flex items-center gap-1.5 rounded-md bg-[#f5c518] px-2.5 py-1 text-xs font-bold text-black">
                      IMDb {content.imdb_rating}
                      {content.imdb_votes ? (
                        <span className="font-normal opacity-80">({content.imdb_votes})</span>
                      ) : null}
                    </span>
                  )}
                  {content.ratings
                    ?.filter((r) => r.source !== "Internet Movie Database")
                    .map((r) => (
                      <span
                        key={r.source}
                        className="inline-flex items-center gap-1.5 rounded-md border border-border bg-card/60 px-2.5 py-1 text-xs font-semibold text-foreground"
                      >
                        <span className="text-muted-foreground">{r.source}:</span> {r.value}
                      </span>
                    ))}
                </div>
              )}

              {/* Action Buttons */}
              <div className="flex flex-wrap items-center gap-3 pt-2">
                {primaryTrailer && (
                  <Button
                    type="button"
                    variant="brand"
                    onClick={() => logTrailerView(primaryTrailer)}
                  >
                    <Play size={16} fill="currentColor" aria-hidden="true" /> Watch Trailer
                  </Button>
                )}

                <Button
                  type="button"
                  variant="outline"
                  onClick={() => saveMutation.mutate()}
                  disabled={saveMutation.isPending}
                  aria-pressed={isSaved}
                  className={isSaved ? "border-primary/40 text-primary" : ""}
                >
                  <Bookmark size={16} fill={isSaved ? "currentColor" : "none"} aria-hidden="true" />
                  {isSaved ? "Saved in Library" : "Save to Watchlist"}
                </Button>

                <Button
                  type="button"
                  variant="outline"
                  onClick={() => setIsRatingModalOpen(true)}
                  className={userRating ? "border-yellow-500/40 text-yellow-400" : ""}
                >
                  <Star size={16} fill={userRating ? "currentColor" : "none"} aria-hidden="true" />
                  {userRating ? `Your Rating: ${userRating}/10` : "Rate Title"}
                </Button>
              </div>

              {/* Overview */}
              <div className="pt-3">
                <h2 className="mb-2 text-sm font-semibold uppercase tracking-wider text-muted-foreground">
                  Overview
                </h2>
                <p className="max-w-4xl text-base leading-relaxed text-foreground/90">
                  {content.overview || "No detailed overview is available for this title."}
                </p>
              </div>

              {/* Directors / Creators */}
              {directors.length > 0 && (
                <div className="pt-2">
                  <span className="mr-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                    {isTv ? "Created / Directed by:" : "Directed by:"}
                  </span>
                  <span className="text-sm font-medium text-foreground">
                    {directors.map((d) => d.name).join(", ")}
                  </span>
                </div>
              )}
            </div>
          </div>
        </div>
      </section>

      {/* WatchMan Verdict & Decision Section */}
      <section className="relative z-20 -mt-8 mx-auto max-w-[1400px] px-4 sm:px-7">
        <WatchmanScoreCard
          contentId={content.id}
          contentType={contentType}
          initialScore={content.watchman_score}
          initialLabel={content.watchman_label}
        />
      </section>

      {/* Detail Body Content */}
      <div className="mx-auto max-w-[1400px] space-y-12 px-4 py-8 sm:px-7">
        {/* Cast Carousel */}
        {topCast.length > 0 && (
          <section aria-labelledby="cast-heading">
            <div className="mb-4">
              <span className="text-[11px] font-extrabold uppercase tracking-[0.16em] text-primary/80">
                Performers
              </span>
              <h2
                id="cast-heading"
                className="mt-1 text-2xl font-semibold tracking-tight text-foreground"
              >
                Top Cast
              </h2>
            </div>

            <ul className="-mx-1 flex gap-4 overflow-x-auto px-1 pb-4 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
              {topCast.map((actor) => (
                <li key={actor.id} className="group w-32 shrink-0 text-center">
                  <div className="mx-auto h-28 w-28 overflow-hidden rounded-full border-2 border-border bg-secondary transition-colors group-hover:border-primary">
                    {actor.profile_url ? (
                      <img
                        src={actor.profile_url}
                        alt={actor.name}
                        className="h-full w-full object-cover"
                        loading="lazy"
                      />
                    ) : (
                      <div className="flex h-full w-full items-center justify-center text-lg font-bold text-muted-foreground">
                        {actor.name[0]}
                      </div>
                    )}
                  </div>
                  <div className="mt-2.5 line-clamp-1 text-xs font-bold text-foreground">
                    {actor.name}
                  </div>
                  {actor.character && (
                    <div className="line-clamp-1 text-[11px] text-muted-foreground">
                      {actor.character}
                    </div>
                  )}
                </li>
              ))}
            </ul>
          </section>
        )}

        {/* Where to Watch — region-aware, live from TMDB (JustWatch). Never fabricated. */}
        <section aria-labelledby="watch-heading" className="border-t border-border pt-8">
          <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
            <div>
              <span className="text-[11px] font-extrabold uppercase tracking-[0.16em] text-primary/80">
                Streaming
              </span>
              <h2
                id="watch-heading"
                className="mt-1 flex items-center gap-2 text-2xl font-semibold tracking-tight text-foreground"
              >
                <MonitorPlay size={22} aria-hidden="true" /> Where to Watch
              </h2>
            </div>
            <label className="block">
              <span className="sr-only">Region</span>
              <select
                className="h-9 rounded-md border border-border bg-secondary px-3 text-sm text-foreground outline-none focus-visible:ring-2 focus-visible:ring-ring"
                value={watchRegion}
                onChange={(e) => setWatchRegion(e.target.value)}
                aria-label="Streaming region"
              >
                {watchRegions.map((r) => (
                  <option key={r.iso_3166_1} value={r.iso_3166_1}>
                    {r.english_name}
                  </option>
                ))}
              </select>
            </label>
          </div>
          {watchProvidersQuery.isLoading ? (
            <div
              className="h-16 animate-pulse rounded-xl border border-border bg-secondary"
              aria-hidden="true"
            />
          ) : !hasOffers ? (
            <p className="max-w-2xl text-sm text-muted-foreground">
              Not available on any tracked streaming service in {watchRegionName}. Availability is
              reported by JustWatch via TMDB and may differ in other regions.
            </p>
          ) : (
            <div className="space-y-4">
              {WATCH_PROVIDER_GROUPS.map((group) => {
                const list = (offers?.[group.key] || []) as OttProvider[];
                if (list.length === 0) return null;
                return (
                  <div key={group.key}>
                    <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                      {group.label}
                    </h3>
                    <ul className="flex flex-wrap gap-3">
                      {list.map((p) => {
                        const logo = imageUrl(p.logo_path, "w185");
                        return (
                          <li
                            key={p.provider_id}
                            title={p.provider_name}
                            className="flex items-center gap-2 rounded-lg border border-border bg-card px-2.5 py-1.5"
                          >
                            {logo ? (
                              <img
                                src={logo}
                                alt=""
                                loading="lazy"
                                className="h-7 w-7 rounded-md object-cover"
                              />
                            ) : (
                              <MonitorPlay
                                size={18}
                                aria-hidden="true"
                                className="text-muted-foreground"
                              />
                            )}
                            <span className="text-xs font-medium text-foreground">
                              {p.provider_name}
                            </span>
                          </li>
                        );
                      })}
                    </ul>
                  </div>
                );
              })}
              {offers?.link && (
                <a
                  href={offers.link}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1.5 text-xs font-medium text-primary hover:underline"
                >
                  View all options on JustWatch <ExternalLink size={13} aria-hidden="true" />
                </a>
              )}
            </div>
          )}
        </section>

        {/* Media gallery — backdrops + posters from TMDB. */}
        {galleryImages.length > 0 && (
          <section aria-labelledby="media-heading" className="border-t border-border pt-8">
            <div className="mb-4">
              <span className="text-[11px] font-extrabold uppercase tracking-[0.16em] text-primary/80">
                Gallery
              </span>
              <h2
                id="media-heading"
                className="mt-1 flex items-center gap-2 text-2xl font-semibold tracking-tight text-foreground"
              >
                <ImageIcon size={22} aria-hidden="true" /> Media
              </h2>
            </div>
            <ul className="-mx-1 flex gap-3 overflow-x-auto px-1 pb-4 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
              {galleryImages.map((img, idx) => {
                const src = imageUrl(img.file_path, "w780");
                if (!src) return null;
                const isPoster = idx >= backdrops.length;
                return (
                  <li
                    key={`${img.file_path}-${idx}`}
                    className={`h-52 shrink-0 overflow-hidden rounded-xl border border-border bg-secondary ${
                      isPoster ? "w-[9.75rem]" : "w-[22rem]"
                    }`}
                  >
                    <img src={src} alt="" loading="lazy" className="h-full w-full object-cover" />
                  </li>
                );
              })}
            </ul>
          </section>
        )}
        <ReviewsSection contentType={contentType} tmdbId={id} contentTitle={content.title} />

        {/* TMDB community reviews — clearly separated from WatchMan's own member reviews above. */}
        {tmdbReviews.length > 0 && (
          <section aria-labelledby="tmdb-reviews-heading" className="border-t border-border pt-8">
            <div className="mb-4">
              <span className="text-[11px] font-extrabold uppercase tracking-[0.16em] text-primary/80">
                From TMDB
              </span>
              <h2
                id="tmdb-reviews-heading"
                className="mt-1 flex items-center gap-2 text-2xl font-semibold tracking-tight text-foreground"
              >
                <MessageSquare size={22} aria-hidden="true" /> Community Reviews
              </h2>
              <p className="mt-1 text-xs text-muted-foreground">
                Sourced from The Movie Database — distinct from WatchMan member reviews.
              </p>
            </div>
            <ul className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
              {tmdbReviews.map((review) => {
                const avatar = review.avatar_path
                  ? review.avatar_path.startsWith("/http")
                    ? review.avatar_path.slice(1)
                    : imageUrl(review.avatar_path, "w185")
                  : null;
                const rating = review.rating;
                const authorName = review.author || "TMDB user";
                const created = review.created_at
                  ? new Date(review.created_at).toLocaleDateString(undefined, {
                      year: "numeric",
                      month: "short",
                      day: "numeric",
                    })
                  : null;
                return (
                  <li key={review.id} className="rounded-2xl border border-border bg-card/50 p-4">
                    <div className="mb-2 flex items-center gap-3">
                      <span className="grid h-9 w-9 shrink-0 place-items-center overflow-hidden rounded-full border border-border bg-secondary text-sm font-semibold text-foreground">
                        {avatar ? (
                          <img
                            src={avatar}
                            alt=""
                            loading="lazy"
                            className="h-full w-full object-cover"
                          />
                        ) : (
                          authorName[0]?.toUpperCase() || "U"
                        )}
                      </span>
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-sm font-semibold text-foreground">
                          {authorName}
                        </p>
                        {created && <p className="text-xs text-muted-foreground">{created}</p>}
                      </div>
                      {typeof rating === "number" && rating > 0 && (
                        <span className="inline-flex shrink-0 items-center gap-1 rounded-full bg-secondary px-2 py-0.5 text-xs font-semibold text-foreground">
                          <Star size={12} aria-hidden="true" className="text-amber-400" />
                          {rating}/10
                        </span>
                      )}
                    </div>
                    <p className="line-clamp-6 whitespace-pre-line text-sm leading-relaxed text-muted-foreground">
                      {review.content}
                    </p>
                    {review.url && (
                      <a
                        href={review.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="mt-2 inline-flex items-center gap-1 text-xs font-medium text-primary hover:underline"
                      >
                        Read full review on TMDB
                        <ExternalLink size={11} aria-hidden="true" />
                      </a>
                    )}
                  </li>
                );
              })}
            </ul>
          </section>
        )}

        {/* Similar Recommendations Section */}
        {similarItems.length > 0 && (
          <section className="border-t border-border pt-8" aria-labelledby="similar-heading">
            <div className="mb-4">
              <span className="text-[11px] font-extrabold uppercase tracking-[0.16em] text-primary/80">
                Discover More
              </span>
              <h2
                id="similar-heading"
                className="mt-1 text-2xl font-semibold tracking-tight text-foreground"
              >
                Similar Titles You Might Enjoy
              </h2>
            </div>

            <ul className="-mx-1 flex snap-x gap-4 overflow-x-auto px-1 pb-4 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
              {similarItems.map((item) => (
                <li
                  key={`${item.content_type}-${item.id || item.tmdb_id}`}
                  className="w-[42vw] shrink-0 snap-start sm:w-[30vw] md:w-44 lg:w-48"
                >
                  <ContentCard content={item} />
                </li>
              ))}
            </ul>
          </section>
        )}
      </div>

      {/* Rating Dialog */}
      <RatingModal
        isOpen={isRatingModalOpen}
        onClose={() => setIsRatingModalOpen(false)}
        title={content.title}
        initialRating={userRating || 0}
        onRate={handleRate}
      />

      {/* Video Trailer Modal */}
      <VideoModal
        isOpen={Boolean(selectedVideo)}
        onClose={() => setSelectedVideo(null)}
        video={selectedVideo}
        title={content.title}
      />
    </div>
  );
}
