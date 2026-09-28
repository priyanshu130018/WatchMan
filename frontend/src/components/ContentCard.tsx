import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate } from "@tanstack/react-router";
import { Bookmark, Check, Film, Loader2, Play, Star, Tv } from "lucide-react";

import { useAuthStore } from "@/store/authStore";
import { type ContentItem, imageUrl } from "@/types/content";
import { rating as formatRating, year as formatYear } from "@/utils/format";
import { userService } from "@/services/user";
import { getApiErrorMessage } from "@/lib/api";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

export interface ContentCardProps {
  content: ContentItem;
  showTypeBadge?: boolean;
  showReason?: boolean;
  aspectRatio?: "poster" | "backdrop";
  progress?: number;
  completed?: boolean;
}

import { getContentDetailRoute } from "@/lib/catalogHelpers";
export { getContentDetailRoute };

export function ContentCard({
  content,
  showTypeBadge = true,
  showReason = true,
  progress,
  completed,
}: ContentCardProps) {
  const token = useAuthStore((state) => state.token);
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [imageError, setImageError] = useState(false);

  const effectiveProgress =
    progress !== undefined
      ? progress
      : content.progress !== undefined
        ? content.progress
        : content.progress_percent;
  const isCompleted = completed !== undefined ? completed : content.completed;
  const hasActiveProgress =
    effectiveProgress !== undefined && effectiveProgress > 0 && !isCompleted;

  const { isTv, targetId, detailPath } = getContentDetailRoute(content);

  const favorites = useQuery({
    queryKey: ["favorites"],
    queryFn: userService.favorites,
    enabled: Boolean(token),
  });

  const isSaved =
    favorites.data?.some(
      (item) =>
        item.content_id === content.id ||
        item.movie_id === content.id ||
        (item.content && item.content.tmdb_id === content.tmdb_id),
    ) ??
    content.is_saved ??
    false;

  const saveMutation = useMutation({
    mutationFn: async () => {
      if (!token) {
        navigate({ to: "/login" });
        return;
      }
      if (isSaved) {
        return userService.removeFavorite(content.content_type, content.tmdb_id || content.id);
      }
      return userService.addFavorite({
        content_type: content.content_type,
        tmdb_id: content.tmdb_id || content.id,
        movie_id: content.id,
      });
    },
    onSuccess: async () => {
      if (!token) return;
      await queryClient.invalidateQueries({ queryKey: ["favorites"] });
      await queryClient.invalidateQueries({ queryKey: ["recommendations"] });
      await queryClient.invalidateQueries({ queryKey: ["homepage", "personalized"] });
      toast.success(isSaved ? "Removed from your library." : "Saved to your watchlist.");
    },
    onError: (err) => toast.error(getApiErrorMessage(err)),
  });

  const posterSrc = imageError
    ? undefined
    : content.poster_url || imageUrl(content.poster_path, "w500");
  const releaseYear = formatYear(content.release_date || content.first_air_date);
  const ratingValue = content.vote_average ? formatRating(content.vote_average) : null;
  const reason = content.reason || content.explanation;

  return (
    <article className="group relative min-w-0">
      {/* Poster + stretched link (whole card is clickable via ::after overlay) */}
      <Link
        to={detailPath}
        params={{ id: targetId }}
        aria-label={`${content.title}${releaseYear ? `, ${releaseYear}` : ""}`}
        className="block rounded-xl focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background after:absolute after:inset-0 after:z-0 after:content-['']"
      >
        <div className="relative aspect-[2/3] overflow-hidden rounded-xl bg-secondary ring-1 ring-transparent transition-all duration-200 group-hover:-translate-y-0.5 group-hover:shadow-xl group-hover:shadow-black/40 group-hover:ring-primary/50">
          {posterSrc ? (
            <img
              src={posterSrc}
              alt=""
              loading="lazy"
              onError={() => setImageError(true)}
              className="h-full w-full object-cover transition-transform duration-300 group-hover:scale-[1.045]"
            />
          ) : (
            <div className="flex h-full w-full flex-col items-center justify-center gap-2 p-4 text-center text-muted-foreground">
              {isTv ? <Tv size={32} aria-hidden="true" /> : <Film size={32} aria-hidden="true" />}
              <span className="line-clamp-2 text-xs">{content.title}</span>
            </div>
          )}

          <div className="pointer-events-none absolute inset-0 bg-gradient-to-t from-black/70 to-transparent to-[55%]" />

          {showTypeBadge && (
            <Badge
              variant="secondary"
              className="absolute left-2 top-2 bg-black/60 text-[10px] font-bold tracking-wide text-white backdrop-blur-sm"
            >
              {isTv ? "TV" : "MOVIE"}
            </Badge>
          )}

          {(content.watchman_label || (content.vote_average && content.vote_average > 0)) &&
            (() => {
              const rawLabel =
                content.watchman_label ||
                (content.vote_average
                  ? content.vote_average >= 7.5
                    ? "must_watch"
                    : content.vote_average >= 4.5
                      ? "time_pass"
                      : "skip"
                  : null);
              if (!rawLabel) return null;
              return (
                <span
                  className={cn(
                    "absolute right-2 top-2 z-10 rounded-md px-1.5 py-0.5 text-[9px] font-black tracking-wider uppercase backdrop-blur-md shadow-sm border",
                    rawLabel === "must_watch" &&
                      "bg-amber-400 text-black border-amber-300 font-extrabold",
                    rawLabel === "time_pass" &&
                      "bg-neutral-900/85 text-neutral-300 border-neutral-700 font-medium",
                    rawLabel === "skip" && "bg-red-600 text-white border-red-500 font-extrabold",
                  )}
                >
                  {rawLabel === "must_watch" && "MUST WATCH"}
                  {rawLabel === "time_pass" && "TIME PASS"}
                  {rawLabel === "skip" && "SKIP"}
                </span>
              );
            })()}

          {hasActiveProgress && (
            <div className="absolute inset-x-0 bottom-0 z-20 bg-background/95 backdrop-blur-md px-2.5 py-1.5 border-t border-border/40">
              <div className="flex items-center justify-between text-[10px] font-bold text-foreground mb-1">
                <span className="text-primary">{Math.round(effectiveProgress)}% watched</span>
                {content.runtime ? (
                  <span className="text-muted-foreground font-medium text-[9px]">
                    {Math.max(1, Math.round(content.runtime * (1 - effectiveProgress / 100)))}m left
                  </span>
                ) : null}
              </div>
              <div
                role="progressbar"
                aria-valuenow={Math.round(effectiveProgress)}
                aria-valuemin={0}
                aria-valuemax={100}
                className="h-1.5 w-full overflow-hidden rounded-full bg-secondary/80"
              >
                <div
                  className="h-full bg-primary transition-all duration-300"
                  style={{ width: `${Math.min(100, Math.max(0, effectiveProgress))}%` }}
                />
              </div>
            </div>
          )}

          <span
            className={cn(
              "pointer-events-none absolute left-2.5 z-10 inline-flex translate-y-1 items-center gap-1 rounded-md bg-primary px-2 py-1.5 text-[10px] font-extrabold text-primary-foreground opacity-0 transition-all duration-200 group-hover:translate-y-0 group-hover:opacity-100",
              hasActiveProgress ? "bottom-12" : "bottom-2.5",
            )}
          >
            <Play size={13} fill="currentColor" aria-hidden="true" />{" "}
            {hasActiveProgress ? "Resume" : "Details"}
          </span>
        </div>
      </Link>

      {/* Meta */}
      <div className="pt-3">
        <h3 className="truncate text-sm font-medium text-foreground" title={content.title}>
          {content.title}
        </h3>

        {showReason && reason && (
          <p className="mt-1 line-clamp-1 text-[10px] leading-snug text-primary/80" title={reason}>
            {reason}
          </p>
        )}

        <div className="mt-1 flex items-center justify-between text-xs text-muted-foreground">
          <span>{releaseYear || "N/A"}</span>
          {ratingValue && (
            <span className="flex items-center gap-1 text-foreground/90">
              <Star size={12} className="text-amber-400" fill="currentColor" aria-hidden="true" />
              {ratingValue}
            </span>
          )}
        </div>

        {/* Save button — inline, part of the card. Sits above the stretched-link
            overlay via `relative z-10` so it stays independently clickable. Reuses
            the shared favorites mutation/API (no separate save system). */}
        <button
          type="button"
          onClick={() => saveMutation.mutate()}
          disabled={saveMutation.isPending}
          aria-pressed={isSaved}
          aria-label={isSaved ? `Remove ${content.title} from saved` : `Save ${content.title}`}
          className={cn(
            "relative z-10 mt-2.5 inline-flex w-full items-center justify-center gap-1.5 rounded-md border px-2.5 py-1.5 text-xs font-semibold outline-none transition-colors",
            "focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-60",
            isSaved
              ? "border-primary bg-primary text-primary-foreground hover:bg-watchman-yellow-hover"
              : "border-border bg-secondary/60 text-muted-foreground hover:bg-secondary hover:text-foreground",
          )}
        >
          {saveMutation.isPending ? (
            <Loader2 size={13} className="animate-spin" aria-hidden="true" />
          ) : isSaved ? (
            <Check size={13} aria-hidden="true" />
          ) : (
            <Bookmark size={13} aria-hidden="true" />
          )}
          {saveMutation.isPending
            ? isSaved
              ? "Removing…"
              : "Saving…"
            : isSaved
              ? "Saved"
              : "Save"}
        </button>
      </div>
    </article>
  );
}
