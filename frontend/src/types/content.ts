export type ContentType = "movie" | "tv";

export interface Genre {
  id?: number;
  tmdb_id?: number;
  name: string;
}

export interface CastMember {
  id: number;
  name: string;
  character?: string;
  profile_path?: string;
  profile_url?: string;
  order?: number;
}

export interface CrewMember {
  id: number;
  name: string;
  job?: string;
  department?: string;
  profile_path?: string;
  profile_url?: string;
}

export interface VideoItem {
  id?: string;
  key: string;
  name: string;
  site: string;
  type: string;
  official?: boolean;
}

export interface ContentItem {
  id: number;
  tmdb_id?: number;
  content_type: ContentType;
  title: string;
  original_title?: string;
  overview?: string;
  tagline?: string;
  poster_path?: string;
  poster_url?: string;
  backdrop_path?: string;
  backdrop_url?: string;
  release_date?: string;
  first_air_date?: string;
  vote_average?: number;
  vote_count?: number;
  popularity?: number;
  runtime?: number;
  number_of_seasons?: number;
  number_of_episodes?: number;
  original_language?: string;
  genres?: Genre[];
  cast?: CastMember[];
  crew?: CrewMember[];
  videos?: VideoItem[];
  // External ratings (sourced via OMDb on the backend).
  imdb_rating?: string;
  imdb_votes?: string;
  ratings?: { source: string; value: string }[];
  score?: number;
  recommendation_score?: number;
  content_score?: number;
  collaborative_score?: number;
  popularity_score?: number;
  freshness_score?: number;
  reason?: string;
  explanation?: string;
  is_saved?: boolean;
  watchman_score?: number;
  watchman_label?: "must_watch" | "time_pass" | "skip" | string;
  progress?: number;
  progress_percent?: number;
  completed?: boolean;
  last_watched_at?: string;
  duration_seconds?: number;
  progress_seconds?: number;
}

export interface ContentPagination<T = ContentItem> {
  page: number;
  limit: number;
  total: number;
  total_pages: number;
  results: T[];
}

export function imageUrl(
  path?: string,
  size: "w185" | "w342" | "w500" | "w780" | "w1280" | "original" = "w500",
): string | undefined {
  if (!path) return undefined;
  if (path.startsWith("http://") || path.startsWith("https://")) return path;
  const cleanPath = path.startsWith("/") ? path : `/${path}`;
  return `https://image.tmdb.org/t/p/${size}${cleanPath}`;
}

export function normalizeContentItem(raw: any, defaultType: ContentType = "movie"): ContentItem {
  if (!raw) return {} as ContentItem;

  const contentType: ContentType =
    raw.content_type === "tv" || raw.media_type === "tv" || raw.first_air_date || raw.name
      ? "tv"
      : "movie";

  const title = raw.title || raw.name || raw.original_title || raw.original_name || "Untitled";
  const releaseDate = raw.release_date || raw.first_air_date || raw.year || "";

  const genres: Genre[] = Array.isArray(raw.genres)
    ? raw.genres.map((g: any) =>
        typeof g === "string"
          ? { name: g }
          : { id: g.id || g.tmdb_id, name: g.name || (g.genre && g.genre.name) || `Genre ${g.id}` },
      )
    : Array.isArray(raw.genre_ids)
      ? raw.genre_ids.map((id: number) => ({ id, name: `Genre ${id}` }))
      : [];

  const cast: CastMember[] = Array.isArray(raw.cast)
    ? raw.cast.map((c: any) => ({
        id: c.id,
        name: c.name || (c.person && c.person.name) || "",
        character: c.character,
        profile_path: c.profile_path || (c.person && c.person.profile_path),
        profile_url:
          c.profile_url || imageUrl(c.profile_path || (c.person && c.person.profile_path), "w185"),
        order: c.order,
      }))
    : [];

  const crew: CrewMember[] = Array.isArray(raw.crew)
    ? raw.crew.map((cr: any) => ({
        id: cr.id,
        name: cr.name || (cr.person && cr.person.name) || "",
        job: cr.job,
        department: cr.department,
        profile_path: cr.profile_path || (cr.person && cr.person.profile_path),
        profile_url:
          cr.profile_url ||
          imageUrl(cr.profile_path || (cr.person && cr.person.profile_path), "w185"),
      }))
    : [];

  const rawVideos = raw.videos?.results || raw.videos || [];
  const videos: VideoItem[] = Array.isArray(rawVideos)
    ? rawVideos.map((v: any) => ({
        id: v.id,
        key: v.key,
        name: v.name,
        site: v.site || "YouTube",
        type: v.type,
        official: v.official,
      }))
    : [];

  const posterPath = raw.poster_path;
  const backdropPath = raw.backdrop_path;

  return {
    ...raw,
    id: Number(raw.id || raw.tmdb_id || 0),
    tmdb_id: Number(raw.tmdb_id || raw.id || 0),
    content_type: raw.content_type || contentType || defaultType,
    title,
    original_title: raw.original_title || raw.original_name || title,
    overview: raw.overview || "",
    tagline: raw.tagline || "",
    release_date: releaseDate,
    first_air_date: raw.first_air_date || (contentType === "tv" ? releaseDate : undefined),
    poster_path: posterPath,
    backdrop_path: backdropPath,
    poster_url: raw.poster_url || imageUrl(posterPath, "w500"),
    backdrop_url: raw.backdrop_url || imageUrl(backdropPath, "w1280"),
    vote_average: Number(raw.vote_average ?? raw.tmdb_rating ?? 0),
    vote_count: Number(raw.vote_count ?? 0),
    popularity: Number(raw.popularity ?? 0),
    runtime: raw.runtime ? Number(raw.runtime) : undefined,
    number_of_seasons: raw.number_of_seasons ? Number(raw.number_of_seasons) : undefined,
    number_of_episodes: raw.number_of_episodes ? Number(raw.number_of_episodes) : undefined,
    original_language: raw.original_language,
    genres,
    cast,
    crew,
    videos,
    imdb_rating: raw.imdb_rating ?? raw.imdbRating ?? undefined,
    imdb_votes: raw.imdb_votes ?? raw.imdbVotes ?? undefined,
    ratings: Array.isArray(raw.ratings)
      ? raw.ratings
          .map((r: any) => ({ source: r.source ?? r.Source, value: r.value ?? r.Value }))
          .filter((r: any) => r.source && r.value)
      : undefined,
    score: Number(raw.score ?? raw.recommendation_score ?? 0),
    recommendation_score: Number(raw.recommendation_score ?? raw.score ?? 0),
    content_score: Number(raw.content_score ?? 0),
    collaborative_score: Number(raw.collaborative_score ?? 0),
    popularity_score: Number(raw.popularity_score ?? 0),
    freshness_score: Number(raw.freshness_score ?? 0),
    reason: raw.reason || raw.explanation || undefined,
    explanation: raw.explanation || raw.reason || undefined,
    is_saved: Boolean(raw.is_saved || raw.is_favorite),
    is_favorite: Boolean(raw.is_saved || raw.is_favorite),
    watchman_score: raw.watchman_score !== undefined ? Number(raw.watchman_score) : undefined,
    watchman_label: raw.watchman_label || undefined,
    progress:
      raw.progress !== undefined
        ? Number(raw.progress)
        : raw.progress_percent !== undefined
          ? Number(raw.progress_percent)
          : undefined,
    progress_percent:
      raw.progress_percent !== undefined
        ? Number(raw.progress_percent)
        : raw.progress !== undefined
          ? Number(raw.progress)
          : undefined,
    completed: raw.completed !== undefined ? Boolean(raw.completed) : undefined,
    last_watched_at: raw.last_watched_at || raw.watched_at || undefined,
    duration_seconds: raw.duration_seconds !== undefined ? Number(raw.duration_seconds) : undefined,
    progress_seconds: raw.progress_seconds !== undefined ? Number(raw.progress_seconds) : undefined,
  };
}
