import { getRouteApi, Link } from "@tanstack/react-router";
import { motion } from "framer-motion";
import { Heart, Play, Share2, Star } from "lucide-react";
import { useMovie, useToggleFavorite } from "@/hooks/useMovies";
import { formatMatch, formatRating, formatRuntime, formatYear } from "@/utils/format";
import { Skeleton } from "@/components/common/Skeleton";
import { ErrorState } from "@/components/common/ErrorState";
import { TrailerPlayer } from "@/components/player/TrailerPlayer";
import { MovieGrid } from "@/components/movie/MovieGrid";
import { Button } from "@/components/ui/button";
import { useAuthStore } from "@/store/authStore";
import { toast } from "sonner";

const routeApi = getRouteApi("/movie/$id");

export function MovieDetailsPage() {
  const { id } = routeApi.useParams();
  const { data: m, isLoading, isError, refetch } = useMovie(id);
  const toggle = useToggleFavorite();
  const isAuthed = Boolean(useAuthStore((s) => s.token));

  const share = async () => {
    const url = window.location.href;
    try {
      if (navigator.share) await navigator.share({ title: m?.title, url });
      else {
        await navigator.clipboard.writeText(url);
        toast.success("Link copied");
      }
    } catch {
      /* ignore */
    }
  };

  if (isLoading) {
    return (
      <div className="mx-auto max-w-7xl space-y-6 px-4 py-6 sm:px-6">
        <Skeleton className="h-[50vh] w-full rounded-3xl" />
        <Skeleton className="h-8 w-1/2" />
        <Skeleton className="h-32 w-full" />
      </div>
    );
  }
  if (isError || !m) {
    return (
      <div className="mx-auto max-w-3xl px-4 py-16">
        <ErrorState message="Couldn't load this movie." onRetry={() => refetch()} />
      </div>
    );
  }

  return (
    <div className="pb-12">
      <div className="relative h-[55vh] min-h-[380px] w-full overflow-hidden">
        {m.backdrop_url && (
          <img
            src={m.backdrop_url}
            alt=""
            className="h-full w-full object-cover"
          />
        )}
        <div className="absolute inset-0 bg-gradient-to-t from-background via-background/70 to-background/30" />
      </div>

      <div className="mx-auto -mt-40 max-w-7xl px-4 sm:px-6">
        <motion.div
          initial={{ opacity: 0, y: 24 }}
          animate={{ opacity: 1, y: 0 }}
          className="grid gap-8 md:grid-cols-[240px_1fr]"
        >
          <div className="mx-auto w-40 shrink-0 overflow-hidden rounded-2xl ring-1 ring-white/10 shadow-cinema sm:w-56 md:mx-0 md:w-full">
            {m.poster_url ? (
              <img src={m.poster_url} alt={m.title} className="w-full" />
            ) : (
              <div className="aspect-[2/3] w-full bg-white/5" />
            )}
          </div>

          <div className="space-y-4">
            <div>
              <h1 className="text-3xl font-black tracking-tight sm:text-4xl">
                {m.title}
              </h1>
              {m.tagline && (
                <p className="mt-1 text-sm italic text-muted-foreground">
                  {m.tagline}
                </p>
              )}
            </div>

            <div className="flex flex-wrap items-center gap-2 text-xs">
              {m.rabbit_match != null && (
                <span className="rounded-full gradient-rabbit px-2.5 py-1 font-bold text-white">
                  {formatMatch(m.rabbit_match)} Rabbit Match
                </span>
              )}
              {m.imdb_rating != null && (
                <Stat label="IMDb" value={formatRating(m.imdb_rating)} />
              )}
              {m.tmdb_rating != null && (
                <Stat label="TMDB" value={formatRating(m.tmdb_rating)} />
              )}
              {(m.release_year || m.release_date) && (
                <Chip>{formatYear(m.release_date, m.release_year)}</Chip>
              )}
              {m.runtime && <Chip>{formatRuntime(m.runtime)}</Chip>}
              {m.country && <Chip>{m.country}</Chip>}
            </div>

            <div className="flex flex-wrap gap-2">
              {m.genres?.map((g) => (
                <span
                  key={g.id}
                  className="rounded-full border border-white/10 bg-white/5 px-3 py-1 text-xs"
                >
                  {g.name}
                </span>
              ))}
            </div>

            {m.overview && (
              <p className="max-w-3xl text-sm leading-relaxed text-foreground/90">
                {m.overview}
              </p>
            )}

            <div className="flex flex-wrap gap-2 pt-2">
              {m.trailer_url && (
                <a href={m.trailer_url} target="_blank" rel="noreferrer">
                  <Button className="gradient-rabbit border-0">
                    <Play className="h-4 w-4 fill-current" /> Watch Trailer
                  </Button>
                </a>
              )}
              {isAuthed && (
                <Button
                  variant="secondary"
                  onClick={() =>
                    toggle.mutate({ id: m.id, isFavorite: !!m.is_favorite })
                  }
                >
                  <Heart
                    className={`h-4 w-4 ${m.is_favorite ? "fill-primary text-primary" : ""}`}
                  />
                  {m.is_favorite ? "Favorited" : "Favorite"}
                </Button>
              )}
              <Button variant="secondary" onClick={share}>
                <Share2 className="h-4 w-4" /> Share
              </Button>
            </div>

            <dl className="grid gap-3 pt-4 text-sm sm:grid-cols-2">
              {m.director && <Meta label="Director" value={m.director} />}
              {m.writer && <Meta label="Writer" value={m.writer} />}
              {m.languages?.length ? (
                <Meta label="Languages" value={m.languages.join(", ")} />
              ) : null}
              {m.streaming_platforms?.length ? (
                <Meta
                  label="Streaming"
                  value={m.streaming_platforms.map((p) => p.name).join(", ")}
                />
              ) : null}
            </dl>
          </div>
        </motion.div>

        {m.cast && m.cast.length > 0 && (
          <section className="mt-12">
            <h2 className="mb-4 text-xl font-bold">Cast</h2>
            <div className="flex gap-4 overflow-x-auto scrollbar-hide">
              {m.cast.map((c) => (
                <div key={c.id} className="w-28 shrink-0 text-center">
                  <div className="mx-auto mb-2 h-28 w-28 overflow-hidden rounded-full bg-white/5 ring-1 ring-white/10">
                    {c.profile_url ? (
                      <img
                        src={c.profile_url}
                        alt={c.name}
                        className="h-full w-full object-cover"
                        loading="lazy"
                      />
                    ) : null}
                  </div>
                  <p className="line-clamp-1 text-sm font-medium">{c.name}</p>
                  {c.character && (
                    <p className="line-clamp-1 text-xs text-muted-foreground">
                      {c.character}
                    </p>
                  )}
                </div>
              ))}
            </div>
          </section>
        )}

        {m.trailer_url && (
          <section className="mt-12">
            <h2 className="mb-4 text-xl font-bold">Trailer</h2>
            <TrailerPlayer url={m.trailer_url} title={m.title} />
          </section>
        )}

        {/* eslint-disable-next-line @typescript-eslint/no-explicit-any */}
        {(m as any).more_like_this?.length ? (
          <section className="mt-12">
            <h2 className="mb-4 text-xl font-bold">More Like This</h2>
            {/* eslint-disable-next-line @typescript-eslint/no-explicit-any */}
            <MovieGrid movies={(m as any).more_like_this} columns={4} />
          </section>
        ) : null}

        <div className="mt-12">
          <Link to="/" className="text-sm text-muted-foreground hover:text-foreground">
            ← Back to home
          </Link>
        </div>
      </div>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <span className="inline-flex items-center gap-1 rounded-full bg-black/40 px-2.5 py-1 backdrop-blur">
      <Star className="h-3 w-3 fill-[var(--rabbit-gold)] text-[var(--rabbit-gold)]" />
      <span className="font-semibold">{value}</span>
      <span className="text-muted-foreground">{label}</span>
    </span>
  );
}
function Chip({ children }: { children: React.ReactNode }) {
  return (
    <span className="rounded-full bg-black/40 px-2.5 py-1 backdrop-blur">
      {children}
    </span>
  );
}
function Meta({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-xs uppercase tracking-wider text-muted-foreground">
        {label}
      </dt>
      <dd className="mt-0.5 text-foreground/90">{value}</dd>
    </div>
  );
}
