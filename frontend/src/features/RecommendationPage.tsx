import { useState, type ReactNode } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { Sparkles, RefreshCw, Film, Tv, Info } from "lucide-react";

import { ContentCard } from "@/components/ContentCard";
import { ContentGridSkeleton } from "@/components/Skeletons";
import { EmptyState, ErrorState } from "@/components/States";
import { Button } from "@/components/ui/button";
import { recommendationService } from "@/services/recommendations";
import { useAuthStore } from "@/store/authStore";
import { cn } from "@/lib/utils";

export function RecommendationPage() {
  const user = useAuthStore((s) => s.user);
  const queryClient = useQueryClient();
  const [contentType, setContentType] = useState<"all" | "movie" | "tv">("all");
  const [refreshNotice, setRefreshNotice] = useState("");

  // Fetch recommendations for authenticated users
  const recQuery = useQuery({
    queryKey: ["recommendations", "catalog", contentType, user?.id],
    queryFn: () =>
      recommendationService.getRecommendations({
        contentType,
        limit: 20,
      }),
    enabled: Boolean(user),
  });

  const refreshMutation = useMutation({
    mutationFn: () => recommendationService.refresh(),
    onSuccess: () => {
      setRefreshNotice("Recommendations regenerated based on your latest activity.");
      queryClient.invalidateQueries({ queryKey: ["recommendations"] });
      setTimeout(() => setRefreshNotice(""), 5000);
    },
    onError: () => {
      setRefreshNotice("Could not refresh pipeline right now. Serving cached recommendations.");
      setTimeout(() => setRefreshNotice(""), 5000);
    },
  });

  // 1. Logged-out state: show dedicated sign-in prompt without fake recommendations
  if (!user) {
    return (
      <div className="mx-auto max-w-[1400px] px-4 py-20 sm:px-7">
        <div className="mx-auto max-w-xl text-center">
          <div className="mx-auto mb-5 flex h-16 w-16 items-center justify-center rounded-2xl border border-primary/20 bg-primary/10 text-primary shadow-sm">
            <Sparkles size={32} aria-hidden="true" />
          </div>
          <h1 className="text-3xl font-bold tracking-tight text-foreground sm:text-4xl">
            Personalized Recommendations
          </h1>
          <p className="mt-3.5 text-base text-muted-foreground leading-relaxed">
            Sign in to unlock WatchMan&apos;s hybrid AI recommendation engine. We combine semantic
            content embeddings, collaborative filtering, and your personal watch history to
            recommend titles tailored to your taste.
          </p>
          <div className="mt-8 flex items-center justify-center gap-3">
            <Button asChild variant="brand" size="lg">
              <Link to="/login">Sign in</Link>
            </Button>
            <Button asChild variant="outline" size="lg">
              <Link to="/signup">Create Account</Link>
            </Button>
          </div>
        </div>
      </div>
    );
  }

  const isLoading = recQuery.isLoading;
  const isError = recQuery.isError;
  const error = recQuery.error;
  const refetch = () => recQuery.refetch();

  const items = recQuery.data?.items ?? [];

  // Cold-start detection: backend returns is_cold_start=true or items=[] when the user
  // lacks interaction history, or stamps fallback items with cold_start.
  const isColdStart =
    recQuery.data?.is_cold_start === true ||
    items.length === 0 ||
    items.some((it) => (it.sources ?? []).some((s) => s.includes("cold_start")));

  // Personalized only once real signal exists
  const isPersonalized = items.length > 0 && !isColdStart;
  const displayName =
    user?.full_name?.trim() ||
    user?.username?.trim() ||
    (user?.email ? user.email.split("@")[0] : "");
  const pageTitle =
    isPersonalized && displayName ? `${displayName}, You May Like` : "Personalized Recommendations";

  const typeTabs: { key: "all" | "movie" | "tv"; label: string; icon?: ReactNode }[] = [
    { key: "all", label: "All Recommendations" },
    { key: "movie", label: "Movies Only", icon: <Film size={13} aria-hidden="true" /> },
    { key: "tv", label: "Web Series Only", icon: <Tv size={13} aria-hidden="true" /> },
  ];

  return (
    <div className="mx-auto max-w-[1400px] px-4 py-8 sm:px-7">
      {/* Hero header */}
      <header className="mb-6">
        <div className="mb-1.5 flex items-center gap-2">
          <Sparkles size={18} className="text-primary" aria-hidden="true" />
          <span className="text-[11px] font-extrabold uppercase tracking-[0.16em] text-primary/80">
            Hybrid AI Pipeline
          </span>
        </div>
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1 className="text-3xl font-bold tracking-tight text-foreground sm:text-4xl">
              {pageTitle}
            </h1>
            <p className="mt-2 max-w-2xl text-sm text-muted-foreground">
              {isPersonalized
                ? "Generated by WatchMan's hybrid engine from your saves, likes, ratings, and watch history."
                : "Vector embeddings, collaborative filtering, and taste profiling tailored to your watchlist."}
            </p>
          </div>

          <Button
            type="button"
            variant="brand"
            onClick={() => refreshMutation.mutate()}
            disabled={refreshMutation.isPending}
          >
            <RefreshCw
              size={16}
              aria-hidden="true"
              className={refreshMutation.isPending ? "animate-spin" : ""}
            />
            {refreshMutation.isPending ? "Recalculating…" : "Refresh Feed"}
          </Button>
        </div>
      </header>

      {/* Refresh notice */}
      {refreshNotice && (
        <div
          role="status"
          aria-live="polite"
          className="mb-5 rounded-lg border border-primary/30 bg-primary/10 px-4 py-2.5 text-sm text-foreground"
        >
          {refreshNotice}
        </div>
      )}

      {/* Type filter tabs */}
      <div
        role="tablist"
        aria-label="Recommendation type"
        className="mb-6 flex flex-wrap gap-2 border-b border-border pb-4"
      >
        {typeTabs.map((tab) => {
          const active = contentType === tab.key;
          return (
            <button
              key={tab.key}
              type="button"
              role="tab"
              aria-selected={active}
              onClick={() => setContentType(tab.key)}
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

      {/* Content grid */}
      {isLoading ? (
        <ContentGridSkeleton count={16} />
      ) : isError ? (
        <ErrorState error={error} onRetry={refetch} />
      ) : items.length > 0 ? (
        <>
          {isColdStart && (
            <div className="mb-8 rounded-2xl border border-primary/30 bg-gradient-to-r from-primary/10 to-primary/5 px-6 py-6">
              <div className="flex items-start gap-3">
                <Sparkles size={22} className="mt-0.5 shrink-0 text-primary" aria-hidden="true" />
                <div>
                  <h2 className="text-lg font-semibold text-foreground">
                    Recommendations will adapt as you explore WatchMan
                  </h2>
                  <p className="mt-1.5 max-w-2xl text-sm text-muted-foreground">
                    Here are top titles to get you started. Your personalized feed will refine
                    automatically as you watch, save, like, or rate titles.
                  </p>
                  <div className="mt-4 flex flex-wrap gap-2">
                    <Button asChild variant="brand" size="sm">
                      <Link to="/trending">Explore trending</Link>
                    </Button>
                    <Button asChild variant="outline" size="sm">
                      <Link to="/profile">Set preferred genres</Link>
                    </Button>
                  </div>
                </div>
              </div>
            </div>
          )}
          <ul className="grid grid-cols-2 gap-4 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6">
            {items.map((item) => (
              <li
                key={`${item.content_type || (contentType === "tv" ? "tv" : "movie")}-${item.id || item.tmdb_id}`}
              >
                <ContentCard content={item as any} />
              </li>
            ))}
          </ul>

          <div className="mt-10 flex items-center gap-3 rounded-xl border border-border bg-card/50 px-5 py-4 text-[13px] text-muted-foreground">
            <Info size={18} className="shrink-0 text-primary" aria-hidden="true" />
            <span>
              Want to refine these recommendations? Rate titles you&apos;ve watched, mark favorites,
              or set preferred genres in{" "}
              <Link to="/profile" className="font-medium text-primary hover:underline">
                your Profile
              </Link>
              .
            </span>
          </div>
        </>
      ) : (
        <EmptyState
          title="No recommendations found yet"
          description="Start exploring trending movies and web series and rate titles to train your recommendation model."
          action={
            <Button asChild variant="brand" size="sm">
              <Link to="/trending">Explore trending</Link>
            </Button>
          }
        />
      )}
    </div>
  );
}
