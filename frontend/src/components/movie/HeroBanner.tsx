import { useEffect, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { Link } from "@tanstack/react-router";
import { Info, Play, Star } from "lucide-react";
import type { Movie } from "@/types/movie";
import { formatMatch, formatRating, formatYear } from "@/utils/format";
import { Skeleton } from "@/components/common/Skeleton";
import { Button } from "@/components/ui/button";

export function HeroBanner({
  movies,
  loading,
}: {
  movies?: Movie[];
  loading?: boolean;
}) {
  const [i, setI] = useState(0);
  useEffect(() => {
    if (!movies || movies.length < 2) return;
    const t = setInterval(
      () => setI((n) => (n + 1) % movies.length),
      7000,
    );
    return () => clearInterval(t);
  }, [movies]);

  if (loading) {
    return <Skeleton className="mb-10 h-[60vh] w-full rounded-3xl" />;
  }
  if (!movies || movies.length === 0) return null;

  const m = movies[i];

  return (
    <section className="relative mb-10 h-[70vh] min-h-[420px] overflow-hidden rounded-3xl ring-1 ring-white/5 shadow-cinema">
      <AnimatePresence mode="wait">
        <motion.div
          key={m.id}
          initial={{ opacity: 0, scale: 1.05 }}
          animate={{ opacity: 1, scale: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.9 }}
          className="absolute inset-0"
        >
          {m.backdrop_url ? (
            <img
              src={m.backdrop_url}
              alt={m.title}
              className="h-full w-full object-cover"
            />
          ) : (
            <div className="h-full w-full gradient-rabbit" />
          )}
          <div className="absolute inset-0 bg-gradient-to-t from-background via-background/70 to-transparent" />
          <div className="absolute inset-0 bg-gradient-to-r from-background/90 to-transparent" />
        </motion.div>
      </AnimatePresence>

      <div className="relative z-10 flex h-full max-w-3xl flex-col justify-end gap-4 p-6 sm:p-10">
        <AnimatePresence mode="wait">
          <motion.div
            key={m.id}
            initial={{ opacity: 0, y: 24 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.5 }}
            className="space-y-3"
          >
            <div className="flex flex-wrap items-center gap-2 text-xs">
              {m.rabbit_match != null && (
                <span className="rounded-full gradient-rabbit px-2.5 py-1 font-bold text-white">
                  {formatMatch(m.rabbit_match)} AI Match
                </span>
              )}
              {m.imdb_rating != null && (
                <span className="inline-flex items-center gap-1 rounded-full bg-black/50 px-2.5 py-1 backdrop-blur">
                  <Star className="h-3 w-3 fill-[var(--rabbit-gold)] text-[var(--rabbit-gold)]" />
                  {formatRating(m.imdb_rating)} IMDb
                </span>
              )}
              <span className="rounded-full bg-black/50 px-2.5 py-1 backdrop-blur">
                {formatYear(m.release_date, m.release_year)}
              </span>
              {m.genres?.slice(0, 3).map((g) => (
                <span
                  key={g.id}
                  className="rounded-full bg-black/50 px-2.5 py-1 backdrop-blur"
                >
                  {g.name}
                </span>
              ))}
            </div>

            <h1 className="text-3xl font-black tracking-tight sm:text-5xl">
              {m.title}
            </h1>
            {m.overview && (
              <p className="line-clamp-3 max-w-2xl text-sm text-foreground/80 sm:text-base">
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
              <Link to="/movie/$id" params={{ id: String(m.id) }}>
                <Button variant="secondary">
                  <Info className="h-4 w-4" /> View Details
                </Button>
              </Link>
            </div>
          </motion.div>
        </AnimatePresence>

        {movies.length > 1 && (
          <div className="mt-4 flex gap-2">
            {movies.map((_, idx) => (
              <button
                key={idx}
                onClick={() => setI(idx)}
                aria-label={`Slide ${idx + 1}`}
                className={`h-1.5 rounded-full transition-all ${
                  idx === i ? "w-8 bg-primary" : "w-3 bg-white/30"
                }`}
              />
            ))}
          </div>
        )}
      </div>
    </section>
  );
}
