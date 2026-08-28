import { Link } from "@tanstack/react-router";
import { Heart, Play, Star } from "lucide-react";
import { motion } from "framer-motion";
import type { Movie } from "@/types/movie";
import { formatMatch, formatRating, formatYear } from "@/utils/format";
import { useAuthStore } from "@/store/authStore";
import { useToggleFavorite } from "@/hooks/useMovies";

export function MovieCard({
  movie,
  showMatch = true,
  showRank,
}: {
  movie: Movie;
  showMatch?: boolean;
  showRank?: number;
}) {
  const isAuthed = Boolean(useAuthStore((s) => s.token));
  const toggle = useToggleFavorite();
  const fav = movie.is_favorite ?? false;

  const onFav = (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (!isAuthed) return;
    toggle.mutate({ id: movie.id, isFavorite: fav });
  };

  return (
    <Link
      to="/movie/$id"
      params={{ id: String(movie.id) }}
      className="group block"
    >
      <motion.div
        whileHover={{ y: -4 }}
        transition={{ type: "spring", stiffness: 260, damping: 20 }}
        className="relative overflow-hidden rounded-2xl bg-card ring-1 ring-white/5 shadow-cinema"
      >
        <div className="relative aspect-[2/3] w-full overflow-hidden bg-white/5">
          {movie.poster_url ? (
            <img
              src={movie.poster_url}
              alt={movie.title}
              loading="lazy"
              className="h-full w-full object-cover transition-transform duration-500 group-hover:scale-110"
            />
          ) : (
            <div className="flex h-full items-center justify-center text-xs text-muted-foreground">
              No image
            </div>
          )}

          {showRank != null && (
            <div className="absolute -bottom-2 -left-1 text-[6rem] font-black leading-none tracking-tighter text-white/10 mix-blend-overlay">
              {showRank}
            </div>
          )}

          <div className="pointer-events-none absolute inset-0 bg-gradient-to-t from-black/85 via-black/10 to-transparent opacity-90" />

          <button
            onClick={onFav}
            aria-label={fav ? "Remove favorite" : "Add favorite"}
            className={`absolute right-2 top-2 grid h-8 w-8 place-items-center rounded-full backdrop-blur transition ${
              fav
                ? "bg-primary text-primary-foreground"
                : "bg-black/50 text-white hover:bg-black/80"
            }`}
          >
            <Heart className={`h-4 w-4 ${fav ? "fill-current" : ""}`} />
          </button>

          {showMatch && movie.rabbit_match != null && (
            <div className="absolute left-2 top-2 rounded-full gradient-rabbit px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-white shadow">
              {formatMatch(movie.rabbit_match)} match
            </div>
          )}

          <div className="absolute inset-x-0 bottom-0 p-3">
            <h3 className="line-clamp-1 text-sm font-semibold text-white">
              {movie.title}
            </h3>
            <div className="mt-1 flex items-center gap-2 text-[11px] text-white/70">
              <span>{formatYear(movie.release_date, movie.release_year)}</span>
              {movie.imdb_rating != null && (
                <>
                  <span>•</span>
                  <span className="inline-flex items-center gap-1">
                    <Star className="h-3 w-3 fill-[var(--rabbit-gold)] text-[var(--rabbit-gold)]" />
                    {formatRating(movie.imdb_rating)}
                  </span>
                </>
              )}
            </div>
          </div>

          <div className="pointer-events-none absolute inset-0 flex items-center justify-center opacity-0 transition-opacity group-hover:opacity-100">
            <span className="pointer-events-auto inline-flex items-center gap-1 rounded-full gradient-rabbit px-4 py-2 text-xs font-semibold text-white shadow-cinema">
              <Play className="h-4 w-4 fill-current" /> Quick View
            </span>
          </div>
        </div>
      </motion.div>
    </Link>
  );
}
