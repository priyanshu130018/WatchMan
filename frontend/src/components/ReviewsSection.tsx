import React, { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { Edit2, MessageSquare, Star, Trash2 } from "lucide-react";

import { useAuthStore } from "@/store/authStore";
import { userService } from "@/services/user";
import { getApiErrorMessage } from "@/lib/api";
import { toast } from "sonner";
import { formatTimeAgo } from "@/utils/format";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";

export interface ReviewsSectionProps {
  contentType: "movie" | "tv";
  tmdbId: number;
  contentTitle: string;
}

export function ReviewsSection({ contentType, tmdbId, contentTitle }: ReviewsSectionProps) {
  const user = useAuthStore((state) => state.user);
  const token = useAuthStore((state) => state.token);
  const queryClient = useQueryClient();

  const [page, setPage] = useState(1);
  const [titleInput, setTitleInput] = useState("");
  const [contentInput, setContentInput] = useState("");
  const [ratingInput, setRatingInput] = useState<number | undefined>(undefined);
  const [editingReviewId, setEditingReviewId] = useState<number | null>(null);
  const [formError, setFormError] = useState("");

  const queryKey = ["reviews", contentType, tmdbId, page];

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey,
    queryFn: () => userService.getReviews(contentType, tmdbId, page, 8),
  });

  const submitReviewMutation = useMutation({
    mutationFn: async () => {
      if (editingReviewId) {
        return userService.updateReview(editingReviewId, {
          title: titleInput.trim() || undefined,
          content: contentInput.trim(),
          rating: ratingInput,
        });
      }
      return userService.createReview({
        content_type: contentType,
        tmdb_id: tmdbId,
        title: titleInput.trim() || undefined,
        content: contentInput.trim(),
        rating: ratingInput,
      });
    },
    onSuccess: () => {
      const wasEditing = Boolean(editingReviewId);
      setTitleInput("");
      setContentInput("");
      setRatingInput(undefined);
      setEditingReviewId(null);
      setFormError("");
      queryClient.invalidateQueries({ queryKey: ["reviews", contentType, tmdbId] });
      queryClient.invalidateQueries({ queryKey: ["recommendations"] });
      toast.success(wasEditing ? "Review updated." : "Review posted.");
    },
    onError: (err) => {
      const message = getApiErrorMessage(err);
      setFormError(message);
      toast.error(message);
    },
  });

  const deleteReviewMutation = useMutation({
    mutationFn: (reviewId: number) => userService.deleteReview(reviewId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["reviews", contentType, tmdbId] });
      toast.success("Review deleted.");
    },
    onError: (err) => toast.error(getApiErrorMessage(err)),
  });

  const handleStartEdit = (rev: any) => {
    setEditingReviewId(rev.id);
    setTitleInput(rev.title || "");
    setContentInput(rev.content || "");
    setRatingInput(rev.rating || undefined);
    setFormError("");
  };

  const handleCancelEdit = () => {
    setEditingReviewId(null);
    setTitleInput("");
    setContentInput("");
    setRatingInput(undefined);
    setFormError("");
  };

  const reviews = data?.results || [];

  return (
    <section className="mt-12 border-t border-border pt-8" aria-labelledby="reviews-heading">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <span className="text-[11px] font-extrabold uppercase tracking-[0.16em] text-primary/80">
            Community
          </span>
          <h2
            id="reviews-heading"
            className="mt-1 flex items-center gap-2 text-2xl font-semibold tracking-tight text-foreground"
          >
            <MessageSquare size={22} className="text-primary" aria-hidden="true" />
            Reviews &amp; Discussion
          </h2>
        </div>
        {data?.total !== undefined && (
          <span className="text-sm text-muted-foreground">
            {data.total} {data.total === 1 ? "review" : "reviews"}
          </span>
        )}
      </div>

      {/* Review Submission Form */}
      {token ? (
        <div className="mb-8 rounded-2xl border border-border bg-card/60 p-5">
          <h3 className="mb-3 font-semibold text-foreground">
            {editingReviewId ? "Edit your review" : `Write a review for ${contentTitle}`}
          </h3>

          {formError && (
            <p
              role="alert"
              className="mb-4 rounded-lg bg-destructive/10 px-3 py-2 text-sm text-destructive"
            >
              {formError}
            </p>
          )}

          <form
            onSubmit={(e) => {
              e.preventDefault();
              if (!contentInput.trim()) {
                setFormError("Please write your review thoughts before submitting.");
                return;
              }
              submitReviewMutation.mutate();
            }}
            className="space-y-3"
          >
            <div>
              <label htmlFor="review-title" className="sr-only">
                Review headline
              </label>
              <Input
                id="review-title"
                type="text"
                value={titleInput}
                onChange={(e) => setTitleInput(e.target.value)}
                placeholder="Review headline (optional)"
                maxLength={120}
              />
            </div>

            <div>
              <label htmlFor="review-body" className="sr-only">
                Your review
              </label>
              <textarea
                id="review-body"
                value={contentInput}
                onChange={(e) => setContentInput(e.target.value)}
                placeholder="Share your thoughts on the plot, performances, direction..."
                rows={4}
                className="flex w-full resize-none rounded-md border border-input bg-secondary/40 p-4 text-sm text-foreground shadow-sm transition-colors placeholder:text-muted-foreground focus-visible:border-ring focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/40"
                required
              />
            </div>

            {/* Optional Star Rating Selector */}
            <div
              className="flex flex-wrap items-center gap-2"
              role="radiogroup"
              aria-label="Review score (optional)"
            >
              <span className="text-xs text-muted-foreground shrink-0">Score (optional):</span>
              <div className="flex flex-wrap items-center gap-0.5 sm:gap-1 max-w-full">
                {Array.from({ length: 10 }).map((_, idx) => {
                  const sVal = idx + 1;
                  const isFilled = (ratingInput || 0) >= sVal;
                  return (
                    <button
                      key={sVal}
                      type="button"
                      role="radio"
                      aria-checked={ratingInput === sVal}
                      onClick={() => setRatingInput(ratingInput === sVal ? undefined : sVal)}
                      className="shrink-0 rounded p-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                      aria-label={`Score ${sVal} / 10`}
                    >
                      <Star
                        size={15}
                        className={isFilled ? "text-yellow-400" : "text-muted-foreground/40"}
                        fill={isFilled ? "currentColor" : "none"}
                      />
                    </button>
                  );
                })}
              </div>
              {ratingInput && (
                <span className="ml-1 text-xs font-bold text-yellow-400 shrink-0">
                  {ratingInput}/10
                </span>
              )}
            </div>

            <div className="flex justify-end gap-2 pt-2">
              {editingReviewId && (
                <Button type="button" variant="outline" size="sm" onClick={handleCancelEdit}>
                  Cancel
                </Button>
              )}
              <Button
                type="submit"
                variant="brand"
                size="sm"
                disabled={submitReviewMutation.isPending || !contentInput.trim()}
              >
                {submitReviewMutation.isPending
                  ? "Publishing…"
                  : editingReviewId
                    ? "Update Review"
                    : "Post Review"}
              </Button>
            </div>
          </form>
        </div>
      ) : (
        <div className="mb-8 rounded-2xl border border-border bg-card/40 p-6 text-center">
          <p className="mb-3 text-sm text-muted-foreground">
            Sign in to share your thoughts and rate {contentTitle}.
          </p>
          <Button asChild variant="brand" size="sm">
            <Link to="/login">Log in to write a review</Link>
          </Button>
        </div>
      )}

      {/* Reviews List */}
      {isLoading ? (
        <div className="space-y-4">
          <Skeleton className="h-20 w-full rounded-xl" />
          <Skeleton className="h-20 w-full rounded-xl" />
        </div>
      ) : isError ? (
        <div className="py-8 text-center">
          <p className="text-sm text-destructive">Could not load reviews right now.</p>
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="mt-3"
            onClick={() => refetch()}
          >
            Try again
          </Button>
        </div>
      ) : reviews.length === 0 ? (
        <div className="py-8 text-center text-sm text-muted-foreground">
          No reviews yet. Be the first to share your thoughts!
        </div>
      ) : (
        <div className="space-y-4">
          {reviews.map((rev) => {
            const isOwnReview = Boolean(
              user && (rev.user_id === user.id || rev.author?.id === user.id),
            );
            const authorName = rev.author?.full_name || rev.author?.username || "WatchMan User";
            const initial = authorName[0]?.toUpperCase() || "U";

            return (
              <div
                key={rev.id}
                className="relative overflow-hidden rounded-2xl border border-border bg-card/40 p-5"
              >
                <div className="mb-3 flex flex-wrap items-start justify-between gap-3">
                  <div className="flex items-center gap-3 min-w-0 flex-1">
                    <Avatar className="h-9 w-9 shrink-0">
                      <AvatarFallback className="text-xs">{initial}</AvatarFallback>
                    </Avatar>
                    <div className="min-w-0 flex-1">
                      <div className="truncate text-sm font-semibold text-foreground">
                        {authorName}
                      </div>
                      <div className="text-xs text-muted-foreground">
                        {rev.created_at ? formatTimeAgo(rev.created_at) : "recently"}
                      </div>
                    </div>
                  </div>

                  <div className="flex items-center gap-2 shrink-0">
                    {rev.rating !== null && rev.rating !== undefined && (
                      <span className="inline-flex shrink-0 items-center gap-1 rounded-full bg-yellow-400/10 px-2.5 py-1 text-xs font-bold text-yellow-400">
                        <Star
                          size={12}
                          fill="currentColor"
                          aria-hidden="true"
                          className="shrink-0"
                        />
                        {rev.rating}/10
                      </span>
                    )}

                    {isOwnReview && (
                      <div className="ml-1 flex items-center gap-1 shrink-0">
                        <button
                          type="button"
                          onClick={() => handleStartEdit(rev)}
                          className="rounded-lg p-1.5 text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                          aria-label="Edit review"
                        >
                          <Edit2 size={14} />
                        </button>
                        <button
                          type="button"
                          onClick={() => {
                            if (window.confirm("Are you sure you want to delete this review?")) {
                              deleteReviewMutation.mutate(rev.id);
                            }
                          }}
                          className="rounded-lg p-1.5 text-muted-foreground transition-colors hover:bg-secondary hover:text-destructive focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                          aria-label="Delete review"
                        >
                          <Trash2 size={14} />
                        </button>
                      </div>
                    )}
                  </div>
                </div>

                {rev.title && (
                  <h3 className="mb-1.5 text-base font-bold text-foreground break-words [overflow-wrap:anywhere]">
                    {rev.title}
                  </h3>
                )}
                <p className="whitespace-pre-line text-sm leading-relaxed text-foreground/90 break-words [overflow-wrap:anywhere]">
                  {rev.content}
                </p>
              </div>
            );
          })}
        </div>
      )}
    </section>
  );
}
