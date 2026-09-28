import React, { useState, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate } from "@tanstack/react-router";
import {
  Heart,
  History,
  Trash2,
  CheckCircle2,
  User,
  Save,
  Film,
  Tv,
  Star,
  ExternalLink,
  Loader2,
  Pencil,
  X,
  Plus,
  Check,
  LogOut,
  Sparkles,
  Calendar,
} from "lucide-react";

import { ContentCard } from "@/components/ContentCard";
import { ContentGridSkeleton } from "@/components/Skeletons";
import { EmptyState, ErrorState } from "@/components/States";
import { userService } from "@/services/user";
import type { SavedItem } from "@/types/user";
import { useAuthStore } from "@/store/authStore";
import { getApiErrorMessage } from "@/lib/api";
import { toast } from "sonner";
import { normalizeContentItem } from "@/types/content";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { cn } from "@/lib/utils";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogFooter,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import { Badge } from "@/components/ui/badge";
import { authService } from "@/services/auth";

const AVAILABLE_GENRES = [
  { id: 28, name: "Action" },
  { id: 12, name: "Adventure" },
  { id: 16, name: "Animation" },
  { id: 35, name: "Comedy" },
  { id: 80, name: "Crime" },
  { id: 99, name: "Documentary" },
  { id: 18, name: "Drama" },
  { id: 10751, name: "Family" },
  { id: 14, name: "Fantasy" },
  { id: 36, name: "History" },
  { id: 27, name: "Horror" },
  { id: 10402, name: "Music" },
  { id: 9648, name: "Mystery" },
  { id: 10749, name: "Romance" },
  { id: 878, name: "Science Fiction" },
  { id: 10770, name: "TV Movie" },
  { id: 53, name: "Thriller" },
  { id: 10752, name: "War" },
  { id: 37, name: "Western" },
];

function PageHeader({
  eyebrow,
  title,
  description,
  icon,
}: {
  eyebrow: string;
  title: string;
  description: string;
  icon?: React.ReactNode;
}) {
  return (
    <div className="mb-6">
      <div className="flex items-center gap-2">
        {icon}
        <span className="text-[11px] font-extrabold uppercase tracking-[0.16em] text-primary/80">
          {eyebrow}
        </span>
      </div>
      <h1 className="mt-1 text-3xl font-extrabold tracking-tight text-foreground">{title}</h1>
      <p className="mt-1 text-sm text-muted-foreground">{description}</p>
    </div>
  );
}

export function Guard({ children }: { children: React.ReactNode }) {
  const user = useAuthStore((state) => state.user);
  const authReady = useAuthStore((state) => state.authReady);

  // Still restoring a (possibly valid) session — show a neutral loading state
  // rather than flashing the "sign in required" screen to an authed user.
  if (!user && !authReady) {
    return (
      <div
        className="mx-auto flex max-w-[1400px] items-center justify-center px-4 py-32 sm:px-7"
        role="status"
        aria-live="polite"
      >
        <div className="flex flex-col items-center gap-3 text-muted-foreground">
          <Loader2 size={28} className="animate-spin text-primary" aria-hidden="true" />
          <span className="text-sm">Restoring your session…</span>
        </div>
      </div>
    );
  }

  if (!user) {
    return (
      <div className="mx-auto max-w-[1400px] px-4 py-20 text-center sm:px-7">
        <Card className="mx-auto max-w-md p-2">
          <CardContent className="pt-6">
            <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-primary/15">
              <User size={32} className="text-primary" aria-hidden="true" />
            </div>
            <h2 className="mb-2 text-xl font-bold text-foreground">Sign in required</h2>
            <p className="mb-6 text-sm leading-relaxed text-muted-foreground">
              Please sign in or create an account to view your library, personal watch history, and
              customize AI recommendation preferences.
            </p>
            <div className="flex justify-center gap-3">
              <Button asChild variant="brand">
                <Link to="/login">Sign In</Link>
              </Button>
              <Button asChild variant="outline">
                <Link to="/signup">Create Account</Link>
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>
    );
  }
  return <>{children}</>;
}

export function SavedContentPage() {
  const queryClient = useQueryClient();
  const [filterType, setFilterType] = useState<"all" | "movie" | "tv">("all");
  // De-dupes removals: holds saved-row ids whose delete request is already in flight.
  const removingRef = React.useRef<Set<number>>(new Set());

  const savedQuery = useQuery({
    queryKey: ["saved"],
    queryFn: userService.favorites,
    refetchInterval: 30_000,
  });

  const removeMutation = useMutation({
    mutationFn: ({
      contentType,
      tmdbId,
    }: {
      savedId: number;
      contentType: string;
      tmdbId: number;
    }) => userService.removeFavorite(contentType, tmdbId),
    // Optimistic: drop the row from the cache immediately so the UI feels instant.
    // The visible list and the tab counts both read from this cache, so both update now.
    onMutate: async ({ savedId }) => {
      await queryClient.cancelQueries({ queryKey: ["saved"] });
      const previous = queryClient.getQueryData<SavedItem[]>(["saved"]);
      queryClient.setQueryData<SavedItem[]>(["saved"], (old) =>
        (old ?? []).filter((it) => it.id !== savedId),
      );
      return { previous };
    },
    // Roll back to the exact previous list (position + count) if the request fails.
    onError: (err, _vars, context) => {
      if (context?.previous) queryClient.setQueryData(["saved"], context.previous);
      toast.error(getApiErrorMessage(err));
    },
    onSuccess: () => toast.success("Removed from your library."),
    // Reconcile with the server once settled: a successful delete can't be resurrected
    // by a stale cache, and a failed one is corrected. Runs even if the user navigated away.
    onSettled: (_data, _err, { savedId }) => {
      removingRef.current.delete(savedId);
      queryClient.invalidateQueries({ queryKey: ["saved"] });
      queryClient.invalidateQueries({ queryKey: ["favorites"] });
      queryClient.invalidateQueries({ queryKey: ["recommendations"] });
    },
  });

  const handleRemove = (savedId: number, contentType: string, tmdbId: number) => {
    if (removingRef.current.has(savedId)) return; // ignore repeat clicks while pending
    removingRef.current.add(savedId);
    removeMutation.mutate({ savedId, contentType, tmdbId });
  };

  const allItems = savedQuery.data || [];
  const typeOf = (item: any) => item.content?.content_type || (item.movie_id ? "movie" : "tv");
  const filteredItems = allItems.filter((item) =>
    filterType === "all" ? true : typeOf(item) === filterType,
  );

  const filters: {
    key: "all" | "movie" | "tv";
    label: string;
    icon?: React.ReactNode;
    count: number;
  }[] = [
    { key: "all", label: "All Saved", count: allItems.length },
    {
      key: "movie",
      label: "Movies",
      icon: <Film size={13} aria-hidden="true" />,
      count: allItems.filter((i) => typeOf(i) === "movie").length,
    },
    {
      key: "tv",
      label: "Web Series",
      icon: <Tv size={13} aria-hidden="true" />,
      count: allItems.filter((i) => typeOf(i) === "tv").length,
    },
  ];

  return (
    <Guard>
      <div className="mx-auto max-w-[1400px] px-4 py-8 sm:px-7">
        <PageHeader
          eyebrow="Personal Library"
          title="Saved Content"
          description="Movies and web series you've bookmarked to watch later."
          icon={<Heart size={20} className="text-primary" aria-hidden="true" />}
        />

        {/* Filter Tabs */}
        <div
          className="mb-6 flex flex-wrap items-center gap-2 border-b border-border pb-3"
          role="tablist"
          aria-label="Filter saved content"
        >
          {filters.map((f) => (
            <button
              key={f.key}
              type="button"
              role="tab"
              aria-selected={filterType === f.key}
              onClick={() => setFilterType(f.key)}
              className={cn(
                "inline-flex items-center gap-1.5 rounded-md px-3.5 py-1.5 text-sm font-semibold transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                filterType === f.key
                  ? "bg-brand-gradient text-watchman-black"
                  : "bg-secondary text-muted-foreground hover:text-foreground",
              )}
            >
              {f.icon} {f.label} ({f.count})
            </button>
          ))}
        </div>

        {savedQuery.isLoading ? (
          <ContentGridSkeleton count={8} />
        ) : savedQuery.isError ? (
          <ErrorState error={savedQuery.error} onRetry={() => savedQuery.refetch()} />
        ) : filteredItems.length > 0 ? (
          <ul className="grid grid-cols-2 gap-4 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6">
            {filteredItems.map((item) => {
              const raw = item.content || {
                id: item.content_id || item.movie_id,
                tmdb_id: item.content_id || item.movie_id,
                content_type: item.movie_id ? "movie" : "tv",
                title: `Title #${item.content_id || item.movie_id}`,
                poster_path: null,
                backdrop_path: null,
                vote_average: 0,
                vote_count: 0,
              };
              const cardItem = normalizeContentItem(
                raw,
                (raw.content_type as any) || (item.movie_id ? "movie" : "tv"),
              );
              return (
                <li key={item.id} className="group relative">
                  <ContentCard content={cardItem} />
                  <button
                    type="button"
                    onClick={(e) => {
                      e.preventDefault();
                      e.stopPropagation();
                      handleRemove(item.id, cardItem.content_type, cardItem.tmdb_id || cardItem.id);
                    }}
                    aria-label={`Remove ${cardItem.title} from saved`}
                    className="absolute right-2.5 top-2.5 z-10 flex h-8 w-8 items-center justify-center rounded-full border border-white/20 bg-black/75 text-destructive backdrop-blur transition-transform hover:scale-110 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  >
                    <Trash2 size={15} />
                  </button>
                </li>
              );
            })}
          </ul>
        ) : (
          <EmptyState
            title="No saved titles"
            description={
              allItems.length === 0
                ? "You haven't saved any movies or web series yet. Explore the catalog and click 'Save' to bookmark your favorites."
                : "No titles match this filter tab."
            }
            icon={<Heart size={36} className="text-muted-foreground" aria-hidden="true" />}
            action={
              <Button asChild variant="brand">
                <Link to="/">Discover Movies &amp; Series</Link>
              </Button>
            }
          />
        )}
      </div>
    </Guard>
  );
}

export const Favorites = SavedContentPage;

export function WatchHistoryPage() {
  const queryClient = useQueryClient();
  const historyQuery = useQuery({
    queryKey: ["watchHistory"],
    queryFn: userService.history,
    refetchInterval: 30_000,
  });

  const removeMutation = useMutation({
    mutationFn: (id: number) => userService.removeHistory(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["watchHistory"] });
      queryClient.invalidateQueries({ queryKey: ["history"] });
      queryClient.invalidateQueries({ queryKey: ["recommendations"] });
      toast.success("Removed from watch history.");
    },
    onError: (err) => toast.error(getApiErrorMessage(err)),
  });

  const items = historyQuery.data || [];

  return (
    <Guard>
      <div className="mx-auto max-w-[1400px] px-4 py-8 sm:px-7">
        <PageHeader
          eyebrow="Playback Activity"
          title="Watch History"
          description="Track your viewing progress across movies and web-series episodes."
          icon={<History size={20} className="text-primary" aria-hidden="true" />}
        />

        {historyQuery.isLoading ? (
          <div className="flex flex-col gap-3">
            {[1, 2, 3, 4].map((i) => (
              <div
                key={i}
                className="h-20 animate-pulse rounded-xl bg-secondary/60"
                aria-hidden="true"
              />
            ))}
          </div>
        ) : historyQuery.isError ? (
          <ErrorState error={historyQuery.error} onRetry={() => historyQuery.refetch()} />
        ) : items.length > 0 ? (
          <ul className="flex flex-col gap-3">
            {items.map((item) => {
              const content = item.content;
              const type = content?.content_type || (item.movie_id ? "movie" : "tv");
              const linkTo =
                type === "tv"
                  ? `/web-series/${content?.tmdb_id || item.movie_id}`
                  : `/movie/${content?.tmdb_id || item.movie_id}`;
              const progressPct = Math.min(100, Math.max(0, Math.round(item.progress || 0)));

              return (
                <li
                  key={item.id}
                  className="flex items-center justify-between gap-4 rounded-xl border border-border bg-card px-5 py-4"
                >
                  <div className="flex min-w-0 flex-1 items-center gap-4">
                    <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-lg bg-secondary">
                      {type === "tv" ? (
                        <Tv size={20} className="text-primary" aria-hidden="true" />
                      ) : (
                        <Film size={20} className="text-primary" aria-hidden="true" />
                      )}
                    </div>

                    <div className="min-w-0 flex-1">
                      <Link
                        to={linkTo}
                        className="block truncate text-base font-semibold text-foreground hover:text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                      >
                        {content?.title || `Title #${item.content_id || item.movie_id}`}
                      </Link>

                      <div className="mt-1.5 flex items-center gap-2.5 text-[13px] text-muted-foreground">
                        <span>
                          {item.completed ? (
                            <span className="inline-flex items-center gap-1 text-primary">
                              <CheckCircle2 size={13} aria-hidden="true" /> Finished
                            </span>
                          ) : (
                            `Progress: ${progressPct}%`
                          )}
                        </span>
                        <span aria-hidden="true">•</span>
                        <span>
                          {new Date(item.watched_at).toLocaleDateString(undefined, {
                            month: "short",
                            day: "numeric",
                            year: "numeric",
                          })}
                        </span>
                      </div>

                      {!item.completed && progressPct > 0 && (
                        <div
                          className="mt-2 h-1 w-full max-w-[240px] overflow-hidden rounded-full bg-secondary"
                          role="progressbar"
                          aria-valuenow={progressPct}
                          aria-valuemin={0}
                          aria-valuemax={100}
                        >
                          <div
                            className="h-full rounded-full bg-primary"
                            style={{ width: `${progressPct}%` }}
                          />
                        </div>
                      )}
                    </div>
                  </div>

                  <div className="flex shrink-0 items-center gap-2">
                    <Button asChild variant="ghost" size="sm">
                      <Link to={linkTo}>
                        <ExternalLink size={14} aria-hidden="true" /> View
                      </Link>
                    </Button>
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon"
                      onClick={() => removeMutation.mutate(item.id)}
                      aria-label="Remove from history"
                      className="text-muted-foreground hover:text-destructive"
                    >
                      <Trash2 size={16} />
                    </Button>
                  </div>
                </li>
              );
            })}
          </ul>
        ) : (
          <EmptyState
            title="No watch history yet"
            description="Movies and series you stream or log progress on will appear here so you can pick up where you left off."
            icon={<History size={36} className="text-muted-foreground" aria-hidden="true" />}
            action={
              <Button asChild variant="brand">
                <Link to="/">Discover Content</Link>
              </Button>
            }
          />
        )}
      </div>
    </Guard>
  );
}

export const HistoryPage = WatchHistoryPage;

export function ProfilePage() {
  const user = useAuthStore((state) => state.user);
  const setUser = useAuthStore((state) => state.setUser);
  const clear = useAuthStore((state) => state.clear);
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [editing, setEditing] = useState(false);
  const [fullName, setFullName] = useState(user?.full_name || "");
  const [username, setUsername] = useState(user?.username || "");
  const [avatarUrl, setAvatarUrl] = useState(user?.avatar_url || "");
  const [errorMsg, setErrorMsg] = useState("");
  const [isSaving, setIsSaving] = useState(false);

  const savedQuery = useQuery({
    queryKey: ["saved"],
    queryFn: userService.favorites,
    enabled: Boolean(user),
  });
  const historyQuery = useQuery({
    queryKey: ["watchHistory"],
    queryFn: userService.history,
    enabled: Boolean(user),
  });
  const ratingsQuery = useQuery({
    queryKey: ["ratings"],
    queryFn: userService.ratings,
    enabled: Boolean(user),
  });

  // Favorite genres only in this UI. The backend contract still carries
  // disliked_genres; it is preserved on save and never surfaced here.
  const prefQuery = useQuery({
    queryKey: ["userPreferences"],
    queryFn: userService.getPreferences,
    enabled: Boolean(user),
  });
  const [genreDialogOpen, setGenreDialogOpen] = useState(false);
  const [genreDraft, setGenreDraft] = useState<number[]>([]);

  // Keep the form fields mirrored to the authoritative user record while NOT
  // editing, so view mode always reflects the latest saved data.
  useEffect(() => {
    if (user && !editing) {
      setFullName(user.full_name || "");
      setUsername(user.username || "");
      setAvatarUrl(user.avatar_url || "");
    }
  }, [user, editing]);

  const startEditing = () => {
    // Seed the draft form from the current user record.
    setFullName(user?.full_name || "");
    setUsername(user?.username || "");
    setAvatarUrl(user?.avatar_url || "");
    setErrorMsg("");
    setEditing(true);
  };

  const cancelEditing = () => {
    // Discard any unsaved edits and return to view mode.
    setFullName(user?.full_name || "");
    setUsername(user?.username || "");
    setAvatarUrl(user?.avatar_url || "");
    setErrorMsg("");
    setEditing(false);
  };

  const handleUpdate = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMsg("");
    setIsSaving(true);
    try {
      const updated = await userService.updateProfile({
        full_name: fullName.trim() || undefined,
        username: username.trim() || undefined,
        avatar_url: avatarUrl.trim() || undefined,
      });
      setUser(updated);
      toast.success("Profile updated.");
      setEditing(false); // Return to view mode only after a successful save.
    } catch (err) {
      const message = getApiErrorMessage(err);
      setErrorMsg(message);
      toast.error(message);
    } finally {
      setIsSaving(false);
    }
  };

  const savedFavIds = prefQuery.data?.favorite_genres ?? [];

  const openGenreDialog = () => {
    setGenreDraft(prefQuery.data?.favorite_genres ?? []);
    setGenreDialogOpen(true);
  };

  const toggleDraftGenre = (id: number) => {
    setGenreDraft((prev) =>
      prev.includes(id) ? prev.filter((g) => g !== id) : [...prev, id],
    );
  };

  // Single batched save. We send the EXISTING disliked_genres back untouched so
  // the recommendation backend keeps whatever negative signal it already stored.
  const savePrefs = useMutation({
    mutationFn: (favorite_genres: number[]) =>
      userService.updatePreferences({
        favorite_genres,
        disliked_genres: prefQuery.data?.disliked_genres ?? [],
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["userPreferences"] });
      queryClient.invalidateQueries({ queryKey: ["recommendations"] });
      toast.success("Preferences saved.");
      setGenreDialogOpen(false);
    },
    onError: (err) => toast.error(getApiErrorMessage(err)),
  });

  const handleSignOut = () => {
    authService.logout();
    clear();
    toast.success("Signed out.");
    navigate({ to: "/" });
  };

  const genreName = (id: number) =>
    AVAILABLE_GENRES.find((g) => g.id === id)?.name ??
    prefQuery.data?.favorite_genre_details?.find((d) => d.tmdb_id === id || d.id === id)?.name ??
    `Genre ${id}`;

  const initial = user?.email ? user.email[0].toUpperCase() : "U";
  const joinedLabel = user?.created_at
    ? new Date(user.created_at).toLocaleDateString(undefined, { month: "long", year: "numeric" })
    : null;

  const displayName = user?.full_name || user?.username || "WatchMan Member";

  const stats = [
    {
      key: "saved",
      icon: <Heart size={16} aria-hidden="true" />,
      label: "Saved Items",
      query: savedQuery,
      color: "text-primary",
    },
    {
      key: "watched",
      icon: <History size={16} aria-hidden="true" />,
      label: "Titles Watched",
      query: historyQuery,
      color: "text-primary",
    },
    {
      key: "ratings",
      icon: <Star size={16} aria-hidden="true" />,
      label: "Ratings Submitted",
      query: ratingsQuery,
      color: "text-primary",
    },
  ];

  return (
    <Guard>
      <div className="mx-auto max-w-[1400px] px-4 py-8 sm:px-7">
        {editing ? (
          /* ----------------------------- EDIT MODE ----------------------------- */
          <Card>
            <CardHeader className="flex flex-row items-center gap-4 space-y-0">
              <Avatar className="h-16 w-16 border-2 border-primary">
                <AvatarImage src={avatarUrl || undefined} alt="" />
                <AvatarFallback className="text-2xl">{initial}</AvatarFallback>
              </Avatar>
              <div>
                <CardTitle className="text-xl">Edit profile</CardTitle>
                <p className="mt-1 text-sm text-muted-foreground">
                  Update your public account details.
                </p>
              </div>
            </CardHeader>
            <CardContent>
              <form onSubmit={handleUpdate} className="space-y-5">
                <div className="grid gap-5 sm:grid-cols-2">
                  <div className="space-y-1.5">
                    <Label htmlFor="profile-name">Full name</Label>
                    <Input
                      id="profile-name"
                      type="text"
                      value={fullName}
                      onChange={(e) => setFullName(e.target.value)}
                      placeholder="e.g. Priyanshu Verma"
                      disabled={isSaving}
                    />
                  </div>
                  <div className="space-y-1.5">
                    <Label htmlFor="profile-username">Username handle</Label>
                    <Input
                      id="profile-username"
                      type="text"
                      value={username}
                      onChange={(e) => setUsername(e.target.value)}
                      placeholder="e.g. cinephile99"
                      disabled={isSaving}
                    />
                  </div>
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="profile-avatar">Avatar image URL</Label>
                  <Input
                    id="profile-avatar"
                    type="url"
                    value={avatarUrl}
                    onChange={(e) => setAvatarUrl(e.target.value)}
                    placeholder="https://images.unsplash.com/photo-..."
                    disabled={isSaving}
                  />
                </div>

                {errorMsg && (
                  <p
                    role="alert"
                    aria-live="assertive"
                    className="rounded-lg border border-destructive/30 bg-destructive/10 px-3.5 py-2.5 text-sm text-destructive"
                  >
                    {errorMsg}
                  </p>
                )}

                <div className="flex flex-col-reverse gap-3 border-t border-border pt-5 sm:flex-row sm:justify-end">
                  <Button
                    type="button"
                    variant="outline"
                    onClick={cancelEditing}
                    disabled={isSaving}
                    className="w-full sm:w-auto"
                  >
                    <X size={15} aria-hidden="true" /> Cancel
                  </Button>
                  <Button type="submit" variant="brand" disabled={isSaving} className="w-full sm:w-auto">
                    <Save size={15} aria-hidden="true" /> {isSaving ? "Saving…" : "Save Changes"}
                  </Button>
                </div>
              </form>
            </CardContent>
          </Card>
        ) : (
          /* ----------------------------- VIEW MODE ----------------------------- */
          <div className="space-y-8">
            <Card>
              <CardContent className="flex flex-col gap-6 p-6 sm:flex-row sm:items-center sm:justify-between sm:p-8">
                <div className="flex flex-col items-center gap-5 text-center sm:flex-row sm:text-left">
                  <Avatar className="h-24 w-24 border-2 border-primary sm:h-28 sm:w-28">
                    <AvatarImage src={user?.avatar_url || undefined} alt="" />
                    <AvatarFallback className="text-3xl">{initial}</AvatarFallback>
                  </Avatar>
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center justify-center gap-2 sm:justify-start">
                      <h1 className="text-2xl font-extrabold tracking-tight text-foreground sm:text-3xl">
                        {displayName}
                      </h1>
                      <Badge variant="secondary" className="gap-1">
                        <CheckCircle2 size={13} aria-hidden="true" /> Member
                      </Badge>
                    </div>
                    <p className="mt-1.5 truncate text-sm text-muted-foreground">{user?.email}</p>
                    <div className="mt-2 flex flex-wrap items-center justify-center gap-x-4 gap-y-1 text-[13px] text-muted-foreground sm:justify-start">
                      {user?.username && <span>@{user.username}</span>}
                      {joinedLabel && (
                        <span className="inline-flex items-center gap-1">
                          <Calendar size={13} aria-hidden="true" /> Joined {joinedLabel}
                        </span>
                      )}
                    </div>
                  </div>
                </div>
                <div className="flex shrink-0 justify-center sm:justify-end">
                  <Button type="button" variant="brand" onClick={startEditing} className="w-full sm:w-auto">
                    <Pencil size={15} aria-hidden="true" /> Edit Profile
                  </Button>
                </div>
              </CardContent>
            </Card>
            <section aria-labelledby="profile-activity-heading">
              <h2
                id="profile-activity-heading"
                className="mb-3 text-sm font-semibold uppercase tracking-wider text-muted-foreground"
              >
                Your activity
              </h2>
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
                {stats.map((s) => {
                  const q = s.query;
                  return (
                    <Card key={s.label}>
                      <CardContent className="p-5">
                        <div className="flex items-center justify-between">
                          <span className="text-sm font-medium text-muted-foreground">{s.label}</span>
                          <span className={s.color}>{s.icon}</span>
                        </div>
                        {q.isLoading ? (
                          <div
                            className="mt-2 flex items-center gap-2 text-muted-foreground"
                            role="status"
                            aria-live="polite"
                          >
                            <Loader2 size={16} className="animate-spin" aria-hidden="true" />
                            <span className="text-sm">Loading…</span>
                          </div>
                        ) : q.isError ? (
                          <div className="mt-2 flex items-center gap-2">
                            <span className="text-sm font-medium text-destructive" role="alert">
                              Couldn&apos;t load
                            </span>
                            <button
                              type="button"
                              onClick={() => q.refetch()}
                              className="rounded-md border border-border px-2 py-0.5 text-xs font-semibold text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                            >
                              Retry
                            </button>
                          </div>
                        ) : (
                          <div className="mt-1 text-3xl font-bold text-foreground">
                            {q.data?.length ?? 0}
                          </div>
                        )}
                      </CardContent>
                    </Card>
                  );
                })}
              </div>
            </section>
            <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
              <Card className="lg:col-span-2">
                <CardHeader className="flex flex-row items-start justify-between gap-3 space-y-0">
                  <div>
                    <CardTitle className="flex items-center gap-2 text-base">
                      <Sparkles size={17} className="text-primary" aria-hidden="true" /> My preferences
                    </CardTitle>
                    <p className="mt-1 text-sm text-muted-foreground">
                      Favorite genres tune your personalized recommendations.
                    </p>
                  </div>
                  <Button type="button" variant="outline" size="sm" onClick={openGenreDialog}>
                    <Plus size={15} aria-hidden="true" />
                    {savedFavIds.length ? "Edit genres" : "Add favorite genres"}
                  </Button>
                </CardHeader>
                <CardContent>
                  {prefQuery.isLoading ? (
                    <div
                      className="flex items-center gap-2 text-muted-foreground"
                      role="status"
                      aria-live="polite"
                    >
                      <Loader2 size={16} className="animate-spin" aria-hidden="true" />
                      <span className="text-sm">Loading preferences…</span>
                    </div>
                  ) : prefQuery.isError ? (
                    <div className="flex items-center gap-3">
                      <span className="text-sm font-medium text-destructive" role="alert">
                        Couldn&apos;t load your preferences.
                      </span>
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        onClick={() => prefQuery.refetch()}
                      >
                        Retry
                      </Button>
                    </div>
                  ) : savedFavIds.length === 0 ? (
                    <p className="text-sm text-muted-foreground">
                      No favorite genres yet. Add a few so your recommendations feel more like you.
                    </p>
                  ) : (
                    <div className="flex flex-wrap gap-2">
                      {savedFavIds.map((id) => (
                        <Badge key={id} variant="secondary" className="px-3 py-1 text-[13px]">
                          {genreName(id)}
                        </Badge>
                      ))}
                    </div>
                  )}
                </CardContent>
              </Card>
              <Card>
                <CardHeader>
                  <CardTitle className="text-base">Account</CardTitle>
                  <p className="mt-1 text-sm text-muted-foreground">
                    Jump to your library or sign out.
                  </p>
                </CardHeader>
                <CardContent className="flex flex-col gap-2">
                  <Button asChild variant="outline" className="justify-start">
                    <Link to="/saved">
                      <Heart size={15} aria-hidden="true" /> Saved content
                    </Link>
                  </Button>
                  <Button asChild variant="outline" className="justify-start">
                    <Link to="/history">
                      <History size={15} aria-hidden="true" /> Watch history
                    </Link>
                  </Button>
                  <Button
                    type="button"
                    variant="ghost"
                    onClick={handleSignOut}
                    className="justify-start text-destructive hover:text-destructive"
                  >
                    <LogOut size={15} aria-hidden="true" /> Sign out
                  </Button>
                </CardContent>
              </Card>
            </div>
          </div>
        )}
      </div>
      {/* Favorite-genre picker: batch edit -> single Save. Cancel discards the draft. */}
      <Dialog open={genreDialogOpen} onOpenChange={setGenreDialogOpen}>
        <DialogContent className="max-w-xl">
          <DialogHeader>
            <DialogTitle>Favorite genres</DialogTitle>
            <DialogDescription>
              Pick the genres you love. These feed your personalized recommendations.
            </DialogDescription>
          </DialogHeader>
          <div className="flex flex-wrap gap-2 py-1" role="group" aria-label="Select favorite genres">
            {AVAILABLE_GENRES.map((g) => {
              const selected = genreDraft.includes(g.id);
              return (
                <button
                  type="button"
                  key={g.id}
                  onClick={() => toggleDraftGenre(g.id)}
                  aria-pressed={selected}
                  className={cn(
                    "inline-flex items-center gap-1 rounded-full border px-3.5 py-2 text-[13px] font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                    selected
                      ? "border-primary/60 bg-primary/15 text-primary"
                      : "border-border bg-secondary text-foreground/80 hover:text-foreground",
                  )}
                >
                  {selected && <Check size={13} aria-hidden="true" />}
                  {g.name}
                </button>
              );
            })}
          </div>
          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => setGenreDialogOpen(false)}
              disabled={savePrefs.isPending}
            >
              Cancel
            </Button>
            <Button
              type="button"
              variant="brand"
              onClick={() => savePrefs.mutate(genreDraft)}
              disabled={savePrefs.isPending}
            >
              <Save size={15} aria-hidden="true" />
              {savePrefs.isPending ? "Saving…" : "Save preferences"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Guard>
  );
}

export const Profile = ProfilePage;
