import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { Heart, Trash2 } from "lucide-react";

import { userService } from "@/services/user";
import { getApiErrorMessage } from "@/lib/api";
import { toast } from "sonner";
import { normalizeContentItem, imageUrl } from "@/types/content";
import { rating as formatRating, year as formatYear } from "@/utils/format";
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetClose } from "@/components/ui/sheet";
import { Button } from "@/components/ui/button";

export interface SavedDrawerProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

/**
 * Right-to-left slide-over listing the user's saved movies and web series.
 * Rendered from the navbar so Saved is reachable from any page without a
 * full navigation.
 */
export function SavedDrawer({ open, onOpenChange }: SavedDrawerProps) {
  const queryClient = useQueryClient();

  const savedQuery = useQuery({
    queryKey: ["saved"],
    queryFn: userService.favorites,
    enabled: open,
    staleTime: 30_000,
  });

  const removeMutation = useMutation({
    mutationFn: ({ contentType, tmdbId }: { contentType: string; tmdbId: number }) =>
      userService.removeFavorite(contentType, tmdbId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["saved"] });
      queryClient.invalidateQueries({ queryKey: ["favorites"] });
      toast.success("Removed from your library.");
    },
    onError: (err) => toast.error(getApiErrorMessage(err)),
  });

  const items = savedQuery.data || [];

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="flex w-full flex-col gap-0 p-0 sm:max-w-md">
        <SheetHeader className="border-b border-border px-5 py-4">
          <SheetTitle className="flex items-center gap-2">
            <Heart size={18} className="text-pink-500" aria-hidden="true" /> Saved content
          </SheetTitle>
        </SheetHeader>

        <div className="flex-1 overflow-y-auto px-5 py-4">
          {savedQuery.isLoading ? (
            <p className="py-10 text-center text-sm text-muted-foreground">
              Loading your saved titles…
            </p>
          ) : savedQuery.isError ? (
            <p className="py-10 text-center text-sm text-destructive">
              Could not load saved content.
            </p>
          ) : items.length === 0 ? (
            <div className="py-12 text-center">
              <Heart size={32} className="mx-auto text-pink-500/70" aria-hidden="true" />
              <p className="mt-3 text-sm text-muted-foreground">
                You haven't saved anything yet. Tap the bookmark on any title to add it here.
              </p>
              <SheetClose asChild>
                <Button asChild variant="brand" size="sm" className="mt-4">
                  <Link to="/">Discover titles</Link>
                </Button>
              </SheetClose>
            </div>
          ) : (
            <ul className="flex flex-col gap-3">
              {items.map((item: any) => {
                const raw = item.content || {
                  id: item.content_id || item.movie_id,
                  tmdb_id: item.tmdb_id || item.content_id || item.movie_id,
                  content_type: item.content_type || (item.movie_id ? "movie" : "tv"),
                  title: `Title #${item.content_id || item.movie_id}`,
                  poster_path: null,
                };
                const card = normalizeContentItem(
                  raw,
                  (raw.content_type as any) || (item.movie_id ? "movie" : "tv"),
                );
                const isTv = card.content_type === "tv";
                const detailPath = isTv ? "/web-series/$id" : "/movie/$id";
                const targetId = String(card.tmdb_id || card.id);
                const poster = card.poster_url || imageUrl(card.poster_path, "w185");
                const releaseYear = formatYear(card.release_date || card.first_air_date);
                const ratingValue = card.vote_average ? formatRating(card.vote_average) : null;

                return (
                  <li
                    key={item.id}
                    className="flex items-center gap-3 rounded-lg border border-border bg-card/40 p-2"
                  >
                    <SheetClose asChild>
                      <Link
                        to={detailPath}
                        params={{ id: targetId }}
                        className="flex min-w-0 flex-1 items-center gap-3"
                      >
                        <div className="h-[72px] w-12 shrink-0 overflow-hidden rounded-md bg-secondary">
                          {poster ? (
                            <img
                              src={poster}
                              alt=""
                              loading="lazy"
                              className="h-full w-full object-cover"
                            />
                          ) : null}
                        </div>
                        <div className="min-w-0">
                          <p className="truncate text-sm font-medium text-foreground">
                            {card.title}
                          </p>
                          <p className="mt-0.5 text-xs text-muted-foreground">
                            {isTv ? "Web Series" : "Movie"}
                            {releaseYear ? ` · ${releaseYear}` : ""}
                            {ratingValue ? ` · ★ ${ratingValue}` : ""}
                          </p>
                        </div>
                      </Link>
                    </SheetClose>
                    <button
                      type="button"
                      onClick={() =>
                        removeMutation.mutate({
                          contentType: card.content_type,
                          tmdbId: card.tmdb_id || card.id,
                        })
                      }
                      disabled={removeMutation.isPending}
                      aria-label={`Remove ${card.title} from saved`}
                      className="grid h-8 w-8 shrink-0 place-items-center rounded-md text-destructive transition-colors hover:bg-destructive/10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-60"
                    >
                      <Trash2 size={15} />
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </div>

        <div className="border-t border-border px-5 py-3">
          <SheetClose asChild>
            <Button asChild variant="outline" size="sm" className="w-full">
              <Link to="/saved">Open full Saved page</Link>
            </Button>
          </SheetClose>
        </div>
      </SheetContent>
    </Sheet>
  );
}
