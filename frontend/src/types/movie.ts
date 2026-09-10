export type Movie = {
  id: number;
  tmdb_id?: number;
  title: string;
  original_title?: string;
  overview?: string;
  tagline?: string;
  poster_url?: string;
  backdrop_url?: string;
  poster_path?: string;
  backdrop_path?: string;
  release_date?: string;
  vote_average?: number;
  imdb_rating?: number;
  tmdb_rating?: number;
  popularity?: number;
  runtime?: number;
  genres?: Array<{ id?: number; name: string }>;
  cast?: Array<{ id: number; name: string; character?: string; profile_path?: string; profile_url?: string }>;
  crew?: Array<{ id: number; name: string; job?: string }>;
  trailer_url?: string;
  is_favorite?: boolean;
  reason?: string;
};

export type RecommendationMovie = Movie & {
  recommendation_score: number;
  content_score: number;
  collaborative_score: number;
  popularity_score: number;
  reason: string;
};

export function imageUrl(path?: string, size = 'w500') {
  if (!path) return undefined;
  if (path.startsWith('http')) return path;
  return `https://image.tmdb.org/t/p/${size}${path}`;
}

export function normalizeMovie(raw: any): Movie {
  const genres = Array.isArray(raw?.genres) ? raw.genres : Array.isArray(raw?.genre_ids) ? raw.genre_ids.map((id: number) => ({ id, name: `Genre ${id}` })) : [];
  const cast = Array.isArray(raw?.cast) ? raw.cast : [];
  const crew = Array.isArray(raw?.crew) ? raw.crew : [];
  return {
    ...raw,
    id: Number(raw?.id ?? raw?.tmdb_id),
    tmdb_id: raw?.tmdb_id ?? raw?.id,
    poster_url: raw?.poster_url ?? imageUrl(raw?.poster_path, 'w500'),
    backdrop_url: raw?.backdrop_url ?? imageUrl(raw?.backdrop_path, 'w1280'),
    tmdb_rating: raw?.tmdb_rating ?? raw?.vote_average,
    genres,
    cast: cast.map((c: any) => ({ ...c, profile_url: c.profile_url ?? imageUrl(c.profile_path, 'w185') })),
    crew,
  };
}
